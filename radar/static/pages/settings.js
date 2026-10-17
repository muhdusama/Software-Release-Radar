(() => {
  const shell = document.querySelector('.settings-shell');
  const buttons = [...document.querySelectorAll('[data-settings-target]')];
  const sections = [...document.querySelectorAll('[data-settings-section]')];
  const allowed = new Set(sections.map(section => section.dataset.settingsSection));
  function show(name, updateUrl = true) {
    if (!allowed.has(name)) name = 'general';
    buttons.forEach(button => button.classList.toggle('active', button.dataset.settingsTarget === name));
    sections.forEach(section => section.hidden = section.dataset.settingsSection !== name);
    if (updateUrl) history.replaceState(null, '', `?section=${encodeURIComponent(name)}`);
  }
  buttons.forEach(button => button.addEventListener('click', () => show(button.dataset.settingsTarget)));
  const initial = new URLSearchParams(location.search).get('section') || shell.dataset.initialSection || 'general';
  show(initial, false);
})();
