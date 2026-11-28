(() => {
  const root = document.querySelector("[data-notifications]");
  if (!root) {
    return; // Guests have no bell, so nothing is requested.
  }

  const trigger = root.querySelector("[data-notifications-trigger]");
  const badge = root.querySelector("[data-notifications-badge]");
  const unreadText = root.querySelector("[data-notifications-unread-text]");
  const panel = root.querySelector("[data-notifications-panel]");
  const statusEl = root.querySelector("[data-notifications-status]");
  const list = root.querySelector("[data-notifications-list]");
  const moreButton = root.querySelector("[data-notifications-more]");
  const msg = root.dataset;
  const COUNT_INTERVAL = 30_000;

  let unread = Number.parseInt(msg.initialUnread, 10);
  let loaded = false; // The first page is in the list.
  let loading = false;
  let nextUrl = null;
  let lastCountCheck = Date.now();
  const shownIds = new Set();

  function setUnread(count) {
    unread = Math.max(0, count);
    badge.textContent = unread > 9 ? "9+" : String(unread);
    badge.hidden = unread === 0;
    unreadText.textContent = unread > 0 ? msg.msgUnread.replace("{count}", unread) : "";
  }

  function setStatus(text) {
    statusEl.textContent = text;
    statusEl.hidden = !text;
  }

  // DRF builds `next` as an absolute URL; keep only path and query so it stays on this origin.
  function localPath(url) {
    const parsed = new URL(url, location.href);
    return parsed.pathname + parsed.search;
  }

  const relativeTime = (() => {
    const lang = document.documentElement.lang || navigator.language;
    let format;
    try {
      format = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
    } catch {
      format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    }
    const steps = [
      ["year", 365 * 24 * 3600],
      ["month", 30 * 24 * 3600],
      ["week", 7 * 24 * 3600],
      ["day", 24 * 3600],
      ["hour", 3600],
      ["minute", 60],
    ];
    return (date) => {
      const seconds = (date.getTime() - Date.now()) / 1000;
      for (const [unit, size] of steps) {
        if (Math.abs(seconds) >= size) {
          return format.format(Math.round(seconds / size), unit);
        }
      }
      return format.format(0, "second"); // "now"
    };
  })();

  function replyUrl(item) {
    if (item.movie_id == null || item.review_id == null) {
      return null;
    }
    return msg.replyUrlTemplate
      .replace(`/${msg.movieSentinel}/`, `/${item.movie_id}/`)
      .replaceAll("__REVIEW__", String(item.review_id));
  }

  // Message text with {actor} or {amount} filled in; the username goes in <strong>. No innerHTML.
  function describe(item) {
    const text = document.createElement("span");
    text.className = "notification-text";
    if (item.kind === "reply") {
      if (!item.actor_username) {
        text.textContent = msg.msgReplyAnonymous;
        return text;
      }
      const [before, after = ""] = msg.msgReply.split("{actor}");
      const actor = document.createElement("strong");
      actor.textContent = item.actor_username;
      text.append(before, actor, after);
    } else if (item.kind === "frames") {
      text.textContent = msg.msgFrames.replace("{amount}", item.amount ?? "");
    } else if (item.kind === "level_up") {
      text.textContent = msg.msgLevelUp.replace("{amount}", item.amount ?? "");
    } else {
      return null; // A kind this page does not know yet.
    }
    return text;
  }

  function renderItem(item) {
    const text = describe(item);
    if (!text || shownIds.has(item.id)) {
      return null;
    }
    shownIds.add(item.id);
    const li = document.createElement("li");
    li.className = "notification-item";
    li.classList.toggle("is-unread", !item.is_read);
    li.dataset.kind = item.kind;

    const href = item.kind === "reply" ? replyUrl(item) : null;
    const body = document.createElement(href ? "a" : "div");
    body.className = "notification-body";
    if (href) {
      body.href = href;
    }
    const time = document.createElement("time");
    time.className = "notification-time";
    const created = new Date(item.created_at);
    time.dateTime = item.created_at;
    time.title = created.toLocaleString(document.documentElement.lang || undefined);
    time.textContent = relativeTime(created);
    body.append(text, time);
    li.append(body);
    return li;
  }

  async function loadPage(url) {
    loading = true;
    moreButton.disabled = true;
    try {
      const { data } = await apiRequest(url);
      const items = data.results.map(renderItem).filter(Boolean);
      list.append(...items);
      nextUrl = data.next ? localPath(data.next) : null;
      moreButton.hidden = !nextUrl;
      setStatus(list.children.length ? "" : msg.msgEmpty);
      return data.results;
    } finally {
      loading = false;
      moreButton.disabled = false;
    }
  }

  // Opening shows the list and marks everything read at once. The badge goes now; the unread highlight
  // stays until the panel closes, so the new items are still visible as new.
  async function open() {
    trigger.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    const unreadBefore = unread;
    setUnread(0);

    let hasUnread = unreadBefore > 0;
    if (!loaded || unreadBefore > 0) {
      list.replaceChildren();
      shownIds.clear();
      moreButton.hidden = true;
      setStatus(msg.msgLoading);
      try {
        const results = await loadPage(msg.listUrl);
        loaded = true;
        hasUnread = hasUnread || results.some((item) => !item.is_read);
      } catch {
        setStatus(msg.msgError);
        setUnread(unreadBefore);
        return;
      }
      if (!isOpen()) {
        close(false); // Closed while loading: drop the highlight now, not at the next close.
      }
    }
    if (!hasUnread) {
      return;
    }
    // The list is read first: marking first would return every item as read and lose the highlight.
    try {
      await apiRequest(msg.readUrl, { method: "POST" });
    } catch {
      setUnread(unreadBefore);
    }
  }

  function close(restoreFocus) {
    trigger.setAttribute("aria-expanded", "false");
    panel.hidden = true;
    list.querySelectorAll(".is-unread").forEach((item) => item.classList.remove("is-unread"));
    if (restoreFocus) {
      trigger.focus();
    }
  }

  const isOpen = () => trigger.getAttribute("aria-expanded") === "true";

  trigger.addEventListener("click", () => {
    if (isOpen()) {
      close(true);
    } else {
      open();
    }
  });

  moreButton.addEventListener("click", async () => {
    if (!nextUrl || loading) {
      return;
    }
    try {
      await loadPage(nextUrl);
    } catch {
      setStatus(msg.msgError);
    }
  });

  document.addEventListener("click", (event) => {
    if (isOpen() && !root.contains(event.target)) {
      close(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      event.preventDefault();
      close(true);
    }
  });

  async function refreshUnread() {
    lastCountCheck = Date.now();
    try {
      const { data } = await apiRequest(msg.unreadUrl);
      if (!isOpen()) {
        setUnread(Number(data.unread) || 0);
      }
    } catch {
      // Keep the badge as it is; the next visible tab tries again.
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - lastCountCheck >= COUNT_INTERVAL) {
      refreshUnread();
    }
  });

  if (Number.isNaN(unread)) {
    // The context processor is off: ask once instead of showing no badge.
    setUnread(0);
    refreshUnread();
  } else {
    setUnread(unread);
  }
})();
