(() => {
  const profileMenu = document.querySelector(".header-profile");

  if (!profileMenu) return;

  const trigger = profileMenu.querySelector(".header-profile-trigger");

  document.addEventListener("click", (event) => {
    if (profileMenu.open && !profileMenu.contains(event.target)) {
      profileMenu.open = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !profileMenu.open) return;

    profileMenu.open = false;
    trigger?.focus();
  });
})();
