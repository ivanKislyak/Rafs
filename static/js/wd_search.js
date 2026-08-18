(() => {
  const form = document.querySelector("[data-wd-search-form]");

  if (!form) return;

  const queryInput = form.querySelector("#id_query");
  const clearButton = form.querySelector("[data-wd-search-clear]");
  const submitButton = form.querySelector("[data-wd-search-submit]");
  const submitLabel = submitButton?.querySelector(".wd-search-submit-label");

  const updateClearButton = () => {
    if (!queryInput || !clearButton) return;
    clearButton.hidden = queryInput.value.length === 0;
  };

  queryInput?.setAttribute("placeholder", "Например, Бойцовский клуб");
  updateClearButton();

  queryInput?.addEventListener("input", updateClearButton);

  clearButton?.addEventListener("click", () => {
    queryInput.value = "";
    updateClearButton();
    queryInput.focus();
  });

  form.addEventListener("submit", () => {
    form.classList.add("is-loading");
    if (submitButton) submitButton.disabled = true;
    if (submitLabel) submitLabel.textContent = "Ищем";
  });

  document.querySelectorAll("[data-wd-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const qid = button.dataset.wdCopy;
      const label = button.querySelector("[data-wd-copy-label]");

      if (!qid || !label) return;

      try {
        await navigator.clipboard.writeText(qid);
        button.classList.add("is-copied");
        label.textContent = "QID скопирован";

        window.setTimeout(() => {
          button.classList.remove("is-copied");
          label.textContent = "Скопировать QID";
        }, 1800);
      } catch (_error) {
        label.textContent = qid;
      }
    });
  });
})();
