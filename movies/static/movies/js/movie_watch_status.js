(() => {
  document.querySelectorAll(".movie-watch-status").forEach((container) => {
    const buttons = container.querySelectorAll(".movie-watch-status-btn");
    let savedStatus = container.querySelector(".is-active")?.dataset.value ?? null;
    let selectedStatus = savedStatus;
    let saving = false;
    let selectionVersion = 0;

    const render = () => {
      buttons.forEach((button) => {
        const active = button.dataset.value === selectedStatus;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    };

    const save = async () => {
      if (saving) return;
      saving = true;

      // Send requests in order while keeping the latest choice visible and clickable.
      while (selectedStatus !== savedStatus) {
        const requestedStatus = selectedStatus;
        const requestedVersion = selectionVersion;
        const removing = requestedStatus === null;
        try {
          const response = await fetch(container.dataset.url, {
            method: removing ? "DELETE" : "PUT",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": container.dataset.csrf,
              Accept: "application/json",
            },
            body: removing ? undefined : JSON.stringify({ status: requestedStatus }),
          });

          if (!response.ok) {
            throw new Error(container.dataset.errorMessage);
          }

          if (removing) {
            if (response.status !== 204) {
              throw new Error(container.dataset.errorMessage);
            }
          } else {
            const data = await response.json();
            if (data.status !== requestedStatus) {
              throw new Error(container.dataset.errorMessage);
            }
          }

          savedStatus = requestedStatus;
        } catch (error) {
          console.error(error);
          // A failed older request must not discard a more recent click.
          if (selectionVersion === requestedVersion) {
            selectedStatus = savedStatus;
            render();
            window.alert(container.dataset.errorMessage);
          }
        }
      }

      saving = false;
    };

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        if (container.dataset.authenticated !== "true") {
          window.location.href = container.dataset.loginUrl;
          return;
        }

        selectedStatus = selectedStatus === btn.dataset.value ? null : btn.dataset.value;
        selectionVersion += 1;
        render();
        void save();
      });
    });
  });
})();
