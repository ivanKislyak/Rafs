(() => {
  const images = new Map();
  const pending = new WeakSet();

  function preloadImages(container) {
    container.querySelectorAll('.review-vote-button').forEach(button => {
      [button.dataset.enabledSrc, button.dataset.disabledSrc].forEach(src => {
        if (!src || images.has(src)) return;

        const image = new Image();
        image.decoding = 'sync';
        image.src = src;
        images.set(src, image);
        // Decode in advance without delaying clicks or waiting in the handler.
        image.decode?.().catch(() => {});
      });
    });
  }

  // The feed also preloads images in incoming fragments before inserting cards.
  window.RafsReviewVotes = { preloadImages };

  function render(buttons, vote, likes, dislikes) {
    buttons.forEach(button => {
      const value = Number(button.dataset.voteValue);
      const selected = value === vote;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', String(selected));
      const icon = button.querySelector('.review-vote-icon');
      const src = selected
        ? button.dataset.enabledSrc
        : button.dataset.disabledSrc;
      if (icon.getAttribute('src') !== src) icon.src = src;
      const count = value === 1 ? likes : dislikes;
      button.querySelector('.review-vote-count').textContent = count > 0 ? count : '';
    });
  }

  async function vote(root, clickedButton) {
    if (root.dataset.authenticated !== 'true') {
      location.assign(root.dataset.loginUrl);
      return;
    }

    const group = clickedButton.closest('.review-votes');
    const buttons = [...group.querySelectorAll('.review-vote-button')];
    if (pending.has(group) || buttons.some(button => button.disabled)) return;

    const status = group.closest('.review-action-bar').querySelector('.review-vote-status');
    const previous = buttons.map(button => ({
      button,
      selected: button.classList.contains('is-selected'),
      pressed: button.getAttribute('aria-pressed'),
      src: button.querySelector('.review-vote-icon').getAttribute('src'),
      count: button.querySelector('.review-vote-count').textContent,
    }));
    const previousVote = Number(previous.find(item => item.selected)?.button.dataset.voteValue ?? 0);
    const count = value => {
      const item = previous.find(item => Number(item.button.dataset.voteValue) === value);
      return Number(item?.count.trim().replace(/[\s,\u202f]/g, '')) || 0;
    };
    const clickedVote = Number(clickedButton.dataset.voteValue);
    const nextVote = previousVote === clickedVote ? 0 : clickedVote;
    const likes = Math.max(0, count(1) - Number(previousVote === 1) + Number(nextVote === 1));
    const dislikes = Math.max(0, count(-1) - Number(previousVote === -1) + Number(nextVote === -1));

    pending.add(group);
    group.setAttribute('aria-busy', 'true');
    // Keep keyboard focus and normal visuals while blocking this review's clicks.
    buttons.forEach(button => button.setAttribute('aria-disabled', 'true'));
    status.textContent = '';
    render(buttons, nextVote, likes, dislikes);

    let errorMessage = root.dataset.error;
    try {
      const response = await fetch(root.dataset.voteUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': root.querySelector('[name=csrfmiddlewaretoken]')?.value ?? '',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          review_id: group.dataset.reviewId,
          vote_value: clickedButton.dataset.voteValue,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        if (typeof data?.error === 'string') errorMessage = data.error;
        throw new Error();
      }

      const actualVote = Number(data?.user_vote);
      const actualLikes = Number(data?.likes);
      const actualDislikes = Number(data?.dislikes);
      if (![-1, 0, 1].includes(actualVote)
          || !Number.isInteger(actualLikes) || actualLikes < 0
          || !Number.isInteger(actualDislikes) || actualDislikes < 0) {
        throw new Error();
      }
      render(buttons, actualVote, actualLikes, actualDislikes);
    } catch {
      // Restore exactly what was displayed, including counter formatting.
      previous.forEach(({ button, selected, pressed, src, count }) => {
        button.classList.toggle('is-selected', selected);
        button.setAttribute('aria-pressed', pressed);
        button.querySelector('.review-vote-icon').setAttribute('src', src);
        button.querySelector('.review-vote-count').textContent = count;
      });
      status.textContent = errorMessage;
    } finally {
      pending.delete(group);
      group.removeAttribute('aria-busy');
      buttons.forEach(button => button.removeAttribute('aria-disabled'));
    }
  }

  document.querySelectorAll('[data-review-voting]').forEach(root => {
    preloadImages(root);
    root.addEventListener('click', event => {
      const button = event.target.closest('.review-vote-button');
      if (!button || !root.contains(button)) return;
      vote(root, button);
    });
  });
})();
