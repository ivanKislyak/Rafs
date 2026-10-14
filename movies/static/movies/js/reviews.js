(() => {
  document.querySelector('.reviews-container')?.classList.add('activated-category');
  const feed = document.querySelector('[data-reviews-feed]');
  if (!feed) return;
  const list = feed.querySelector('[data-review-list]');
  const more = feed.querySelector('[data-load-more]');
  const status = feed.querySelector('[data-feed-status]');
  const csrf = feed.querySelector('[name=csrfmiddlewaretoken]').value;
  let loading = false;
  let automaticLoading = true;

  async function loadMore() {
    if (loading || more.hidden) return;
    loading = true;
    more.setAttribute('aria-disabled', 'true');
    list.setAttribute('aria-busy', 'true');
    status.textContent = feed.dataset.loading;
    try {
      const url = new URL(more.href, location.href);
      if (url.origin !== location.origin) throw new Error();
      url.searchParams.set('format', 'json');
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (typeof data.html !== 'string') throw new Error();
      const nextUrl = data.next_url ? new URL(data.next_url, location.href) : null;
      if (nextUrl && nextUrl.origin !== location.origin) throw new Error();
      // This fragment is rendered by our Django template with autoescaping enabled.
      const fragment = document.createElement('template');
      fragment.innerHTML = data.html;
      fragment.content.querySelectorAll('.review-comment').forEach((card) => {
        if (!document.getElementById(card.id)) list.append(card);
      });
      more.hidden = !nextUrl;
      if (nextUrl) more.href = nextUrl.href;
      status.textContent = nextUrl ? '' : feed.dataset.end;
      automaticLoading = true;
    } catch {
      automaticLoading = false;
      status.textContent = feed.dataset.error;
    } finally {
      loading = false;
      more.removeAttribute('aria-disabled');
      list.removeAttribute('aria-busy');
    }
  }
  more.addEventListener('click', (event) => {
    event.preventDefault();
    loadMore();
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && automaticLoading) loadMore();
    }, { rootMargin: '300px' });
    observer.observe(feed.querySelector('[data-feed-sentinel]'));
  }

  const dialog = feed.querySelector('#review-delete-dialog');
  let pendingDelete = null;
  let deleteTrigger = null;
  const confirm = dialog.querySelector('[data-delete-review-confirm]');
  const closeDialog = () => dialog.close();
  dialog.querySelector('[data-delete-review-cancel]').addEventListener('click', closeDialog);
  dialog.addEventListener('click', (event) => { if (event.target === dialog) closeDialog(); });
  dialog.addEventListener('close', () => {
    pendingDelete = null;
    confirm.disabled = false;
    deleteTrigger?.focus();
  });
  confirm.addEventListener('click', () => {
    if (!pendingDelete) return;
    confirm.disabled = true;
    pendingDelete.requestSubmit();
  });

  feed.addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    if (!button || !feed.contains(button)) return;
    if (button.matches('[data-delete-review-trigger]')) {
      pendingDelete = button.closest('form');
      deleteTrigger = button;
      if (typeof dialog.showModal !== 'function') {
        if (window.confirm(button.dataset.deleteTitle)) pendingDelete.requestSubmit();
        return;
      }
      dialog.querySelector('[data-delete-dialog-kicker]').textContent = button.dataset.deleteKicker;
      dialog.querySelector('[data-delete-dialog-title]').textContent = button.dataset.deleteTitle;
      dialog.querySelector('[data-delete-dialog-description]').textContent = button.dataset.deleteDescription;
      dialog.showModal();
      dialog.querySelector('[data-delete-review-cancel]').focus();
    } else if (button.matches('[data-replies-toggle]')) {
      const replies = document.getElementById(button.getAttribute('aria-controls'));
      const open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(open));
      replies.hidden = !open;
      button.querySelector('[data-replies-show]').hidden = open;
      button.querySelector('[data-replies-hide]').hidden = !open;
    } else if (button.matches('[data-reply-for], [data-reply-cancel]')) {
      const card = button.closest('.review-comment');
      const container = card.querySelector('.review-reply-container');
      const trigger = card.querySelector('[data-reply-for]');
      const open = !button.matches('[data-reply-cancel]') && !container.classList.contains('is-open');
      container.classList.toggle('is-open', open);
      trigger.classList.toggle('is-active', open);
      trigger.setAttribute('aria-expanded', String(open));
      if (open) container.querySelector('textarea').focus();
      else trigger.focus();
    } else if (button.matches('.review-vote-button')) {
      if (feed.dataset.authenticated !== 'true') {
        location.assign(feed.dataset.loginUrl);
        return;
      }
      const group = button.closest('.review-votes');
      const buttons = [...group.querySelectorAll('button')];
      if (buttons.some((item) => item.disabled)) return;
      const voteStatus = group.closest('.review-action-bar').querySelector('.review-vote-status');
      buttons.forEach((item) => { item.disabled = true; });
      voteStatus.textContent = '';
      try {
        const response = await fetch(feed.dataset.voteUrl, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
          body: JSON.stringify({ review_id: group.dataset.reviewId, vote_value: button.dataset.voteValue }),
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        buttons.forEach((item) => {
          const selected = Number(item.dataset.voteValue) === data.user_vote;
          item.classList.toggle('is-selected', selected);
          item.setAttribute('aria-pressed', String(selected));
          item.querySelector('img').src = selected ? item.dataset.enabledSrc : item.dataset.disabledSrc;
          const count = Number(item.dataset.voteValue) === 1 ? data.likes : data.dislikes;
          item.querySelector('.review-vote-count').textContent = count || '';
        });
      } catch {
        voteStatus.textContent = feed.dataset.error;
      } finally {
        buttons.forEach((item) => { item.disabled = false; });
      }
    }
  });
})();
