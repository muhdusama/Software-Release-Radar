(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ------------------------------------------------------------------ */
  /* Notifications                                                       */
  /* ------------------------------------------------------------------ */
  const toastRegion = $('#toast-region');
  const alertRegion = $('#alert-region');
  const toastMeta = {
    success: { title: 'Success', icon: '✓', duration: 7000 },
    info: { title: 'Information', icon: 'i', duration: 7000 },
    warning: { title: 'Attention', icon: '!', duration: 12000 },
    error: { title: 'Action failed', icon: '×', duration: 0 },
    progress: { title: 'Working', icon: '↻', duration: 0 },
  };

  function removeToast(toast) {
    if (!toast || toast.dataset.leaving === '1') return;
    toast.dataset.leaving = '1';
    toast.classList.add('toast-leaving');
    window.setTimeout(() => toast.remove(), reduceMotion ? 0 : 220);
  }

  function notify(message, type = 'info', options = {}) {
    if (!toastRegion || !message) return null;
    const normalisedMessage = String(message).trim();
    const duplicate = $$('[data-toast="1"]', toastRegion).find((item) => item.dataset.toastMessage === normalisedMessage && item.dataset.toastType === type);
    if (duplicate) {
      const count = Number(duplicate.dataset.duplicateCount || 1) + 1;
      duplicate.dataset.duplicateCount = String(count);
      duplicate.classList.remove('toast-pulse');
      requestAnimationFrame(() => duplicate.classList.add('toast-pulse'));
      return { element: duplicate, update() {}, close() { removeToast(duplicate); } };
    }
    const currentToasts = $$('[data-toast="1"]', toastRegion);
    currentToasts.slice(0, Math.max(0, currentToasts.length - 3)).forEach(removeToast);
    const meta = toastMeta[type] || toastMeta.info;
    const toast = document.createElement('section');
    toast.className = `toast toast-${type}`;
    toast.dataset.toast = '1';
    toast.dataset.toastMessage = normalisedMessage;
    toast.dataset.toastType = type;
    toast.dataset.duplicateCount = '1';
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.setAttribute('aria-atomic', 'true');

    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = meta.icon;

    const copy = document.createElement('div');
    copy.className = 'toast-copy';
    const title = document.createElement('strong');
    title.className = 'toast-title';
    title.textContent = options.title || meta.title;
    const body = document.createElement('span');
    body.textContent = normalisedMessage;
    copy.append(title, body);

    const close = document.createElement('button');
    close.className = 'toast-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.textContent = '×';
    close.addEventListener('click', () => removeToast(toast));

    toast.append(icon, copy, close);
    toastRegion.append(toast);
    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    if (type === 'error' && alertRegion) {
      alertRegion.textContent = normalisedMessage;
    }

    const duration = options.duration ?? meta.duration;
    let timer = null;
    const startTimer = () => {
      if (!duration) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => removeToast(toast), duration);
    };
    const pauseTimer = () => window.clearTimeout(timer);
    toast.addEventListener('mouseenter', pauseTimer);
    toast.addEventListener('mouseleave', startTimer);
    toast.addEventListener('focusin', pauseTimer);
    toast.addEventListener('focusout', startTimer);
    startTimer();

    return {
      element: toast,
      update(nextMessage, nextType = type) {
        const nextMeta = toastMeta[nextType] || toastMeta.info;
        toast.className = `toast toast-${nextType} toast-visible`;
        icon.textContent = nextMeta.icon;
        title.textContent = options.title || nextMeta.title;
        body.textContent = String(nextMessage);
        toast.dataset.toastMessage = String(nextMessage).trim();
        toast.dataset.toastType = nextType;
      },
      close() { removeToast(toast); },
    };
  }

  window.SRR = Object.assign(window.SRR || {}, { notify });

  const flashScript = $('#server-flashes');
  if (flashScript) {
    try {
      const flashes = JSON.parse(flashScript.textContent || '[]');
      flashes.forEach(([category, message], index) => {
        window.setTimeout(() => notify(message, category || 'info'), 80 + (index * 90));
      });
    } catch (error) {
      console.error('Could not parse server notifications.', error);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Navigation and global interaction feedback                          */
  /* ------------------------------------------------------------------ */
  const navToggle = $('[data-nav-toggle]');
  const primaryNav = $('[data-primary-nav]');
  const navBackdrop = $('[data-nav-backdrop]');
  if (navToggle && primaryNav) {
    const setNav = (open) => {
      navToggle.setAttribute('aria-expanded', String(open));
      primaryNav.classList.toggle('nav-open', open);
      document.body.classList.toggle('nav-open', open);
      if (navBackdrop) navBackdrop.hidden = !open;
      if (open) window.setTimeout(() => $('a, button', primaryNav)?.focus(), reduceMotion ? 0 : 120);
      else navToggle.focus({ preventScroll: true });
    };
    navToggle.addEventListener('click', () => setNav(navToggle.getAttribute('aria-expanded') !== 'true'));
    navBackdrop?.addEventListener('click', () => setNav(false));
    primaryNav.addEventListener('click', (event) => { if (event.target.closest('a')) setNav(false); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && document.body.classList.contains('nav-open')) setNav(false); });
  }

  const progress = $('#page-progress');
  let progressTimer = null;
  function startPageProgress() {
    if (!progress) return;
    window.clearTimeout(progressTimer);
    progressTimer = window.setTimeout(() => progress.classList.add('active'), 120);
  }
  function stopPageProgress() {
    window.clearTimeout(progressTimer);
    if (progress) progress.classList.remove('active');
  }
  window.addEventListener('pageshow', stopPageProgress);

  function setButtonBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.classList.add('is-loading');
      button.setAttribute('aria-busy', 'true');
      button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${label || 'Working…'}</span>`;
    } else {
      button.disabled = false;
      button.classList.remove('is-loading');
      button.removeAttribute('aria-busy');
      if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
    }
  }

  $$('form[method="post"]:not([data-no-busy]):not([data-assistant-form])').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.submitting === '1' || !form.checkValidity()) return;
      form.dataset.submitting = '1';
      form.setAttribute('aria-busy', 'true');
      const submitter = event.submitter || $('button[type="submit"], input[type="submit"]', form);
      const message = form.dataset.busyMessage || (submitter ? `${submitter.textContent.trim() || 'Action'} in progress…` : 'Working…');
      setButtonBusy(submitter, true, 'Working…');
      startPageProgress();
      if (form.dataset.busyMessage) notify(message, 'progress', { duration: 5000 });
    });
  });

  $$('a[href]').forEach((link) => {
    link.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.target === '_blank' || link.href.startsWith('mailto:') || link.href.startsWith('javascript:')) return;
      const current = new URL(window.location.href);
      const next = new URL(link.href, window.location.href);
      const sameDocument = current.pathname === next.pathname && current.search === next.search;
      if (!sameDocument && current.origin === next.origin) startPageProgress();
    });
  });

  /* ------------------------------------------------------------------ */
  /* Command palette and keyboard shortcuts                              */
  /* ------------------------------------------------------------------ */
  const commandPalette = $('[data-command-palette]');
  const commandSearch = $('[data-command-search]');
  const commandItems = $$('[data-command-item]');
  const commandEmpty = $('[data-command-empty]');
  let commandIndex = 0;

  function visibleCommandItems() { return commandItems.filter((item) => !item.hidden); }
  function setCommandIndex(index) {
    const visible = visibleCommandItems();
    commandItems.forEach((item) => item.classList.remove('is-active'));
    if (!visible.length) return;
    commandIndex = (index + visible.length) % visible.length;
    visible[commandIndex].classList.add('is-active');
    visible[commandIndex].scrollIntoView({ block: 'nearest' });
  }
  function filterCommands() {
    const query = (commandSearch?.value || '').trim().toLowerCase();
    commandItems.forEach((item) => { item.hidden = Boolean(query) && !(item.dataset.commandSearchText || item.textContent).toLowerCase().includes(query); });
    if (commandEmpty) commandEmpty.hidden = visibleCommandItems().length > 0;
    setCommandIndex(0);
  }
  function setCommandPalette(open) {
    if (!commandPalette) return;
    commandPalette.hidden = !open;
    document.body.classList.toggle('command-open', open);
    if (open) {
      if (commandSearch) commandSearch.value = '';
      filterCommands();
      window.setTimeout(() => commandSearch?.focus(), 0);
    }
  }
  function runCommand(item) {
    if (!item) return;
    const action = item.dataset.commandAction;
    if (action === 'focus-search') {
      setCommandPalette(false);
      if (window.location.pathname !== '/') window.location.href = '/?focus=search';
      else window.SRR?.focusDashboardSearch?.();
      return;
    }
    if (action === 'toggle-density') {
      setCommandPalette(false);
      if (window.location.pathname !== '/') window.location.href = '/?density=toggle';
      else window.SRR?.toggleDashboardDensity?.();
      return;
    }
    if (item.tagName === 'A') window.location.href = item.href;
    else item.click();
  }
  $$('[data-command-open]').forEach((button) => button.addEventListener('click', () => setCommandPalette(true)));
  $$('[data-command-close]').forEach((button) => button.addEventListener('click', () => setCommandPalette(false)));
  commandSearch?.addEventListener('input', filterCommands);
  commandItems.forEach((item) => item.addEventListener('mouseenter', () => setCommandIndex(visibleCommandItems().indexOf(item))));
  commandPalette?.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setCommandIndex(commandIndex + 1); }
    if (event.key === 'ArrowUp') { event.preventDefault(); setCommandIndex(commandIndex - 1); }
    if (event.key === 'Enter') { event.preventDefault(); runCommand(visibleCommandItems()[commandIndex]); }
  });
  document.addEventListener('keydown', (event) => {
    const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setCommandPalette(commandPalette?.hidden !== false); return; }
    if (event.key === 'Escape' && commandPalette && !commandPalette.hidden) { event.preventDefault(); setCommandPalette(false); return; }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === '/') { event.preventDefault(); if (window.location.pathname === '/') window.SRR?.focusDashboardSearch?.(); else window.location.href = '/?focus=search'; }
    if (event.key.toLowerCase() === 'd' && window.location.pathname === '/') window.SRR?.toggleDashboardDensity?.();
    const routeShortcuts = { '1': '/', '2': '/history', '3': '/upgrades', '4': '/fleet', '5': '/portainer', '6': '/assistant', '7': '/settings', '8': '/users' };
    if (routeShortcuts[event.key]) window.location.href = routeShortcuts[event.key];
  });

  /* ------------------------------------------------------------------ */
  /* Small safe rich-text renderer for Assistant fetch responses         */
  /* ------------------------------------------------------------------ */
  function appendInline(target, text) {
    const pattern = /(\*\*.+?\*\*|`[^`]+`|https?:\/\/[^\s]+)/g;
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      if (match.index > cursor) target.append(document.createTextNode(text.slice(cursor, match.index)));
      const token = match[0];
      if (token.startsWith('**')) {
        const strong = document.createElement('strong');
        strong.textContent = token.slice(2, -2);
        target.append(strong);
      } else if (token.startsWith('`')) {
        const code = document.createElement('code');
        code.textContent = token.slice(1, -1);
        target.append(code);
      } else {
        const link = document.createElement('a');
        link.href = token;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = token;
        target.append(link);
      }
      cursor = match.index + token.length;
    }
    if (cursor < text.length) target.append(document.createTextNode(text.slice(cursor)));
  }

  function renderRichText(target, text) {
    target.replaceChildren();
    const lines = String(text || '').replace(/\r/g, '').split('\n');
    let list = null;
    let paragraph = null;

    const closeList = () => { list = null; };
    const ensureParagraph = () => {
      if (!paragraph) {
        paragraph = document.createElement('p');
        target.append(paragraph);
      }
      return paragraph;
    };

    lines.forEach((raw) => {
      const line = raw.trim();
      if (!line) {
        paragraph = null;
        closeList();
        return;
      }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        paragraph = null;
        closeList();
        const level = Math.min(4, heading[1].length + 2);
        const element = document.createElement(`h${level}`);
        appendInline(element, heading[2]);
        target.append(element);
        return;
      }
      const bullet = line.match(/^[-*]\s+(.+)$/);
      const numbered = line.match(/^\d+[.)]\s+(.+)$/);
      if (bullet || numbered) {
        paragraph = null;
        const type = bullet ? 'UL' : 'OL';
        if (!list || list.tagName !== type) {
          list = document.createElement(type.toLowerCase());
          target.append(list);
        }
        const item = document.createElement('li');
        appendInline(item, (bullet || numbered)[1]);
        list.append(item);
        return;
      }
      closeList();
      const p = ensureParagraph();
      if (p.childNodes.length) p.append(document.createElement('br'));
      appendInline(p, line);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Release Assistant                                                   */
  /* ------------------------------------------------------------------ */
  const assistantRoot = $('[data-assistant-root]');
  if (assistantRoot) {
    const trackerFilter = $('#assistant-tracker-filter');
    const trackerOptions = $$('.assistant-tracker-option', assistantRoot);
    const trackerEmpty = $('#assistant-tracker-empty');
    const messageInput = $('#assistant-message');
    const draftStatus = $('#assistant-draft-status');
    const chatMessages = $('#assistant-chat-messages');
    const chatCard = $('.chat-card', assistantRoot);
    const processing = $('#assistant-processing');
    const processingTitle = $('#assistant-processing-title');
    const processingDetail = $('#assistant-processing-detail');
    const processingTime = $('#assistant-processing-time');
    const progressSteps = $$('[data-progress-step]', assistantRoot);
    const cancelButton = $('#assistant-cancel');
    const runUrl = assistantRoot.dataset.runUrl;
    const trackerId = assistantRoot.dataset.trackerId || 'none';
    const draftKey = `softwareReleaseRadarAssistantDraft:${trackerId}`;
    let processingInterval = null;
    let processingStarted = 0;
    let activeController = null;
    let draftTimer = null;

    async function copyText(text, button) {
      try {
        await navigator.clipboard.writeText(String(text || '').trim());
        const original = button?.textContent;
        if (button) { button.textContent = 'Copied'; window.setTimeout(() => { button.textContent = original; }, 1400); }
        notify('Copied Assistant response.', 'success', { duration: 2500 });
      } catch (error) { notify('Could not copy the response.', 'error'); }
    }
    assistantRoot.addEventListener('click', (event) => {
      const direct = event.target.closest('[data-copy-target]');
      if (direct) { const target = $(direct.dataset.copyTarget); if (target) copyText(target.innerText, direct); return; }
      const messageCopy = event.target.closest('[data-copy-message]');
      if (messageCopy) { const content = $('.assistant-rich-text', messageCopy.closest('.message-body')); if (content) copyText(content.innerText, messageCopy); }
    });

    if (trackerFilter) {
      const applyTrackerFilter = () => {
        const query = trackerFilter.value.trim().toLowerCase(); let shown = 0;
        trackerOptions.forEach((option) => { option.hidden = Boolean(query) && !option.dataset.search.includes(query); if (!option.hidden) shown += 1; });
        if (trackerEmpty) trackerEmpty.hidden = shown !== 0;
      };
      trackerFilter.addEventListener('input', applyTrackerFilter);
    }

    $$('.prompt-template', assistantRoot).forEach((button) => {
      button.addEventListener('click', () => {
        if (!messageInput) return;
        messageInput.value = button.dataset.prompt || '';
        messageInput.dispatchEvent(new Event('input'));
        messageInput.focus(); button.classList.add('selected');
        window.setTimeout(() => button.classList.remove('selected'), 500);
        messageInput.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
      });
    });

    function removeChatEmpty() { $('.assistant-chat-empty', chatMessages)?.remove(); }
    function createCopyButton() {
      const button = document.createElement('button'); button.className = 'message-copy'; button.type = 'button'; button.dataset.copyMessage = ''; button.textContent = 'Copy'; return button;
    }
    function addMessage(role, text, options = {}) {
      if (!chatMessages) return null;
      removeChatEmpty();
      const article = document.createElement('article'); article.className = `chat-message ${role}${options.pending ? ' pending' : ''}`;
      const avatar = document.createElement('div'); avatar.className = 'message-avatar'; avatar.setAttribute('aria-hidden', 'true'); avatar.textContent = role === 'user' ? 'U' : 'R';
      const body = document.createElement('div'); body.className = 'message-body';
      const heading = document.createElement('div'); heading.className = 'message-heading';
      const label = document.createElement('strong'); label.textContent = role === 'user' ? 'You' : 'Radar Assistant'; heading.append(label);
      if (role === 'assistant' && !options.pending) heading.append(createCopyButton());
      const content = document.createElement('div'); content.className = 'assistant-rich-text';
      if (options.pending) { const skeleton = document.createElement('div'); skeleton.className = 'thinking-lines'; skeleton.innerHTML = '<span></span><span></span><span></span>'; content.append(skeleton); }
      else renderRichText(content, text);
      body.append(heading, content); article.append(avatar, body); chatMessages.append(article);
      article.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
      return { article, content, heading };
    }

    const thinkingSteps = [
      'Reviewing installed and current versions…', 'Reading upstream release notes…',
      'Checking migrations and compatibility risks…', 'Assessing downtime and rollback requirements…',
      'Preparing a practical recommendation…',
    ];
    function setProgressStep(index) {
      progressSteps.forEach((step, stepIndex) => { step.classList.toggle('active', stepIndex === index); step.classList.toggle('complete', stepIndex < index); });
      if (processingDetail) processingDetail.textContent = thinkingSteps[index] || thinkingSteps.at(-1);
    }
    function startProcessing(action) {
      if (!processing) return;
      processing.hidden = false; processingStarted = Date.now();
      processingTitle.textContent = action === 'analyse' ? 'Analysing meaningful changes…' : 'Preparing your answer…';
      processingTime.textContent = '0s'; setProgressStep(0); chatCard?.setAttribute('aria-busy', 'true');
      processingInterval = window.setInterval(() => {
        const seconds = Math.max(1, Math.round((Date.now() - processingStarted) / 1000));
        processingTime.textContent = `${seconds}s`; setProgressStep(Math.min(thinkingSteps.length - 1, Math.floor(seconds / 5)));
      }, 1000);
    }
    function stopProcessing() {
      window.clearInterval(processingInterval); processingInterval = null;
      if (processing) processing.hidden = true; chatCard?.setAttribute('aria-busy', 'false'); progressSteps.forEach((step) => step.classList.remove('active', 'complete'));
    }
    cancelButton?.addEventListener('click', () => activeController?.abort());

    function upsertAnalysis(answer, model) {
      let panel = $('#latest-analysis');
      if (!panel) { panel = document.createElement('section'); panel.className = 'panel analysis-card'; panel.id = 'latest-analysis'; $('.chat-card', assistantRoot)?.before(panel); }
      panel.innerHTML = '';
      const header = document.createElement('div'); header.className = 'panel-header assistant-section-header';
      const copy = document.createElement('div'); copy.innerHTML = '<span class="section-kicker">LATEST SAVED COMPARISON</span><h2>Upgrade assessment</h2>';
      const meta = document.createElement('p'); meta.textContent = `${model || 'Configured model'} · just now`; copy.append(meta);
      const actions = document.createElement('div'); actions.className = 'analysis-actions';
      const copyButton = document.createElement('button'); copyButton.className = 'analysis-copy'; copyButton.type = 'button'; copyButton.dataset.copyTarget = '#latest-analysis .prose-output'; copyButton.textContent = 'Copy assessment'; actions.append(copyButton);
      header.append(copy, actions);
      const output = document.createElement('div'); output.className = 'prose-output assistant-rich-text'; renderRichText(output, answer);
      panel.append(header, output); panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }

    async function runAssistant(form, submitter) {
      if (form.dataset.submitting === '1') return;
      const action = form.dataset.assistantAction || form.querySelector('[name="action"]')?.value || 'chat';
      const formData = new FormData(form); const question = String(formData.get('message') || '').trim();
      if (action === 'chat' && !question) { messageInput?.focus(); notify('Enter an upgrade question first.', 'warning'); return; }

      form.dataset.submitting = '1'; form.setAttribute('aria-busy', 'true'); setButtonBusy(submitter, true, action === 'analyse' ? 'Analysing…' : 'Thinking…');
      let pending = null;
      if (action === 'chat') { addMessage('user', question); pending = addMessage('assistant', '', { pending: true }); }
      startProcessing(action);
      const progressToast = notify(action === 'analyse' ? 'Reviewing release history and deployment context…' : 'The Assistant is preparing a deployment-aware answer…', 'progress', { title: action === 'analyse' ? 'Analysing release' : 'Assistant thinking' });
      activeController = new AbortController();
      try {
        const response = await fetch(runUrl, { method: 'POST', body: formData, headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' }, credentials: 'same-origin', signal: activeController.signal });
        const payload = await response.json().catch(() => ({ ok: false, error: 'The server returned an unreadable response.' }));
        if (!response.ok || !payload.ok) throw new Error(payload.error || `Request failed with HTTP ${response.status}.`);
        setProgressStep(thinkingSteps.length - 1);
        if (action === 'analyse') upsertAnalysis(payload.answer, payload.model);
        else if (pending) {
          pending.article.classList.remove('pending'); pending.heading.append(createCopyButton()); renderRichText(pending.content, payload.answer);
          if (messageInput) { messageInput.value = ''; sessionStorage.removeItem(draftKey); messageInput.dispatchEvent(new Event('input')); }
          pending.article.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
        }
        progressToast?.close(); notify(payload.message || 'Answer ready.', 'success');
      } catch (error) {
        progressToast?.close();
        const cancelled = error.name === 'AbortError';
        if (pending) {
          pending.article.classList.remove('pending'); pending.article.classList.add(cancelled ? 'cancelled-message' : 'error-message');
          renderRichText(pending.content, cancelled ? 'Request cancelled. Your draft is still available below.' : `I could not complete this request. ${error.message}`);
        }
        notify(cancelled ? 'Assistant request cancelled.' : (error.message || 'The Assistant request failed.'), cancelled ? 'info' : 'error');
      } finally {
        activeController = null; stopProcessing(); form.dataset.submitting = '0'; form.removeAttribute('aria-busy'); setButtonBusy(submitter, false);
      }
    }

    $$('[data-assistant-form]', assistantRoot).forEach((form) => form.addEventListener('submit', (event) => {
      event.preventDefault(); if (!form.checkValidity()) { form.reportValidity(); return; }
      runAssistant(form, event.submitter || $('button[type="submit"]', form));
    }));

    if (messageInput) {
      const savedDraft = sessionStorage.getItem(draftKey); if (savedDraft && !messageInput.value) messageInput.value = savedDraft;
      const updateDraftStatus = () => {
        window.clearTimeout(draftTimer); const value = messageInput.value;
        if (draftStatus) { draftStatus.hidden = !value; draftStatus.classList.remove('saved'); draftStatus.textContent = value ? 'Saving draft…' : ''; }
        draftTimer = window.setTimeout(() => {
          if (value) sessionStorage.setItem(draftKey, value); else sessionStorage.removeItem(draftKey);
          if (draftStatus && value) { draftStatus.hidden = false; draftStatus.classList.add('saved'); draftStatus.textContent = 'Draft saved'; }
        }, 300);
      };
      messageInput.addEventListener('input', updateDraftStatus); if (savedDraft) updateDraftStatus();
      messageInput.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('#assistant-chat-form')?.requestSubmit(); } });
    }
  }
})();
