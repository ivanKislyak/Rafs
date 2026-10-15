(() => {
    const list = document.querySelector("[data-catalog-list]");
    const more = document.querySelector("[data-catalog-more]");
    const status = document.querySelector("[data-catalog-status]");
    const sentinel = document.querySelector("[data-catalog-sentinel]");

    if (!list || !more || !status || !sentinel) return;

    let nextPage = more.dataset.nextPage;
    let loading = false;
    let automaticLoading = true;

    async function loadMore() {
        if (loading || !nextPage) return;

        loading = true;
        more.disabled = true;
        status.textContent = status.dataset.loading;

        try {
            const url = new URL(window.location.href);
            url.searchParams.set("page", nextPage);
            url.searchParams.set("format", "json");

            const response = await fetch(url, {
                headers: { Accept: "application/json" },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (typeof data.html !== "string") {
                throw new Error("Expected HTML in response");
            }

            list.insertAdjacentHTML("beforeend", data.html);

            nextPage = data.next_page;
            more.hidden = !nextPage;
            status.textContent = "";
            automaticLoading = true;
        } catch (error) {
            automaticLoading = false;
            status.textContent = status.dataset.error;
            console.error("Catalog loading failed:", error);
        } finally {
            loading = false;
            more.disabled = false;
        }
    }

    more.addEventListener("click", loadMore);

    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            if (entries.some(entry => entry.isIntersecting)
                && automaticLoading) {
                loadMore();
            }
        }, { rootMargin: "300px" });

        observer.observe(sentinel);
    }
})();