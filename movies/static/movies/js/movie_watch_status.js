const watchStatusButtons = document.querySelectorAll(".movie-watch-status-btn");

watchStatusButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!reviewVoteUserIsAuthenticated) {
      window.location.href = reviewVoteLoginUrl;
      return;
    }

    const container = btn.closest(".movie-watch-status");
    if (!container || container.dataset.pending === "true") {
      return;
    }

    const buttons = container.querySelectorAll(".movie-watch-status-btn");

    container.dataset.pending = "true";
    buttons.forEach((button) => {
      button.disabled = true;
    });

    try {
      const response = await fetch(container.dataset.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": container.dataset.csrf,
        },
        body: JSON.stringify({
          movie_id: container.dataset.movieId,
          status: btn.dataset.value,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || container.dataset.errorMessage);
      }

      buttons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.value === data.status);
      });
    } catch (error) {
      console.error(error);
      window.alert(container.dataset.errorMessage);
    } finally {
      delete container.dataset.pending;
      buttons.forEach((button) => {
        button.disabled = false;
      });
    }
  });
});
