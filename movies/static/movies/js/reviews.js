(() => {
  document.querySelector('.reviews-container')
    ?.classList.add('activated-category');

  const feed = document.querySelector('[data-reviews-feed]');
  if (!feed) return;

  const list = feed.querySelector('[data-review-list]');
  const more = feed.querySelector('[data-load-more]');
  const status = feed.querySelector('[data-feed-status]');

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

      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });

      if (!response.ok) throw new Error();

      const data = await response.json();
      if (typeof data.html !== 'string') throw new Error();

      const nextUrl = data.next_url
        ? new URL(data.next_url, location.href)
        : null;

      if (nextUrl && nextUrl.origin !== location.origin) {
        throw new Error();
      }

      // HTML приходит из нашего Django-шаблона с автоэкранированием.
      const fragment = document.createElement('template');
      fragment.innerHTML = data.html;

      window.RafsReviewVotes.preloadImages(fragment.content);

      fragment.content.querySelectorAll('.review-comment').forEach(card => {
        if (!document.getElementById(card.id)) {
          list.append(card);
        }
      });

      more.hidden = !nextUrl;

      if (nextUrl) {
        more.href = nextUrl.href;
      }

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

  more.addEventListener('click', event => {
    event.preventDefault();
    loadMore();
  });

  const sentinel = feed.querySelector('[data-feed-sentinel]');

  if ('IntersectionObserver' in window && sentinel) {
    const observer = new IntersectionObserver(entries => {
      if (
        entries.some(entry => entry.isIntersecting) &&
        automaticLoading
      ) {
        loadMore();
      }
    }, { rootMargin: '300px' });

    observer.observe(sentinel);
  }

  const dialog = feed.querySelector('#review-delete-dialog');
  let pendingDelete = null;
  let deleteTrigger = null;

  if (dialog) {
    const confirmButton = dialog.querySelector('[data-delete-review-confirm]');
    const cancelButton = dialog.querySelector('[data-delete-review-cancel]');
    const closeDialog = () => dialog.close();

    cancelButton.addEventListener('click', closeDialog);

    dialog.addEventListener('click', event => {
      if (event.target === dialog) closeDialog();
    });

    dialog.addEventListener('close', () => {
      pendingDelete = null;
      confirmButton.disabled = false;
      deleteTrigger?.focus();
    });

    confirmButton.addEventListener('click', () => {
      if (!pendingDelete) return;

      confirmButton.disabled = true;
      pendingDelete.requestSubmit();
    });
  }

  feed.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || !feed.contains(button)) return;

    if (button.matches('[data-delete-review-trigger]')) {
      pendingDelete = button.closest('form');
      deleteTrigger = button;

      if (!dialog || typeof dialog.showModal !== 'function') {
        if (window.confirm(button.dataset.deleteTitle)) {
          pendingDelete.requestSubmit();
        }

        pendingDelete = null;
        return;
      }

      dialog.querySelector('[data-delete-dialog-kicker]').textContent =
        button.dataset.deleteKicker;

      dialog.querySelector('[data-delete-dialog-title]').textContent =
        button.dataset.deleteTitle;

      dialog.querySelector('[data-delete-dialog-description]').textContent =
        button.dataset.deleteDescription;

      dialog.showModal();
      dialog.querySelector('[data-delete-review-cancel]').focus();
    } else if (button.matches('[data-replies-toggle]')) {
      const replies = document.getElementById(
        button.getAttribute('aria-controls')
      );

      const open = button.getAttribute('aria-expanded') !== 'true';

      button.setAttribute('aria-expanded', String(open));
      replies.hidden = !open;
      button.querySelector('[data-replies-show]').hidden = open;
      button.querySelector('[data-replies-hide]').hidden = !open;
    } else if (button.matches('[data-reply-for], [data-reply-cancel]')) {
      const card = button.closest('.review-comment');
      const container = card.querySelector('.review-reply-container');
      const trigger = card.querySelector('[data-reply-for]');

      if (container.querySelector('form[aria-busy="true"]')) return;
      const open = !button.matches('[data-reply-cancel]') &&
        !container.classList.contains('is-open');

      container.classList.toggle('is-open', open);
      trigger.classList.toggle('is-active', open);
      trigger.setAttribute('aria-expanded', String(open));

      if (open) {
        container.querySelector('textarea').focus();
      } else {
        trigger.focus();
      }
    }
  });
})();
