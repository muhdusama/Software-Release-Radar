(() => {
  'use strict';
  const trackerList = document.getElementById('tracker-list');
  const trackerRows = Array.from(document.querySelectorAll('.tracker-row'));
  if (!trackerList || !trackerRows.length) return;

  const storageKeys = {
    page: 'softwareReleaseRadarDashboardPage',
    pageSize: 'softwareReleaseRadarPageSize',
    sortKey: 'softwareReleaseRadarSortKey',
    sortDirection: 'softwareReleaseRadarSortDirection',
    columns: 'softwareReleaseRadarColumnWidths',
    state: 'softwareReleaseRadarDashboardState',
    views: 'softwareReleaseRadarSavedViews',
    density: 'softwareReleaseRadarDensity',
  };
  const fields = {
    filter: document.getElementById('tracker-filter'),
    machine: document.getElementById('machine-filter'),
    connectivity: document.getElementById('connectivity-filter'),
    update: document.getElementById('update-filter'),
    tag: document.getElementById('tag-filter'),
  };
  const collator = new Intl.Collator('en-AU', { numeric: true, sensitivity: 'base' });
  let trackerPage = Number(sessionStorage.getItem(storageKeys.page) || 1);
  let trackerPageSize = Number(localStorage.getItem(storageKeys.pageSize) || 25);
  let trackerSort = {
    key: localStorage.getItem(storageKeys.sortKey) || 'name',
    direction: localStorage.getItem(storageKeys.sortDirection) || 'asc',
    type: 'text',
  };
  let activePreset = 'all';
  let dashboardDensity = localStorage.getItem(storageKeys.density) || 'comfortable';
  if (![10, 25, 50, 100, 200].includes(trackerPageSize)) trackerPageSize = 25;

  function readJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') || fallback; } catch (error) { return fallback; }
  }
  function sortValue(row, key, type) {
    const raw = row.dataset[key] || '';
    if (type === 'number') return Number(raw) || 0;
    if (type === 'date') return raw ? Date.parse(raw) || 0 : 0;
    return raw;
  }
  function compareRows(a, b) {
    const av = sortValue(a, trackerSort.key, trackerSort.type);
    const bv = sortValue(b, trackerSort.key, trackerSort.type);
    let result = 0;
    if (typeof av === 'number' && typeof bv === 'number') result = av - bv;
    else result = collator.compare(String(av), String(bv));
    return trackerSort.direction === 'asc' ? result : -result;
  }
  function applyTrackerSort() {
    trackerRows.sort(compareRows);
    trackerRows.forEach((row) => trackerList.appendChild(row));
    document.querySelectorAll('.tracker-sort-header').forEach((button) => {
      const active = button.dataset.sort === trackerSort.key;
      button.classList.toggle('active', active);
      button.querySelector('.sort-indicator').textContent = active ? (trackerSort.direction === 'asc' ? '▲' : '▼') : '';
    });
    localStorage.setItem(storageKeys.sortKey, trackerSort.key);
    localStorage.setItem(storageKeys.sortDirection, trackerSort.direction);
  }
  function matchesPreset(row, preset = activePreset) {
    if (preset === 'updates') return (row.dataset.update || '').split(/\s+/).includes('update-available');
    if (preset === 'attention') return row.dataset.attention === 'true';
    if (preset === 'paused') return row.dataset.status === 'paused';
    return true;
  }
  function filteredTrackerRows() {
    const q = (fields.filter?.value || '').toLowerCase().trim();
    const tag = (fields.tag?.value || '').toLowerCase().trim();
    const machine = (fields.machine?.value || '').toLowerCase().trim();
    const connectivity = (fields.connectivity?.value || '').toLowerCase().trim();
    const update = (fields.update?.value || '').toLowerCase().trim();
    return trackerRows.filter((row) => {
      const tags = row.dataset.tags ? row.dataset.tags.split(',').map((value) => value.trim()) : [];
      const updateStates = (row.dataset.update || '').split(/\s+/).filter(Boolean);
      return matchesPreset(row)
        && (!q || row.dataset.search.includes(q))
        && (!tag || tags.includes(tag))
        && (!machine || row.dataset.machine === machine)
        && (!connectivity || row.dataset.connectivity === connectivity)
        && (!update || updateStates.includes(update));
    });
  }
  function visibleCheckboxes() { return Array.from(document.querySelectorAll('.tracker-row:not([hidden]) .tracker-checkbox')); }
  function updateFilterSummary(matches) {
    const summary = document.getElementById('active-filter-summary');
    const tokens = document.getElementById('active-filter-tokens');
    const resultCount = document.getElementById('active-filter-result-count');
    if (!summary || !tokens || !resultCount) return;
    const labels = [];
    if (activePreset !== 'all') labels.push(`View: ${activePreset[0].toUpperCase()}${activePreset.slice(1)}`);
    if (fields.filter?.value.trim()) labels.push(`Search: ${fields.filter.value.trim()}`);
    ['machine', 'connectivity', 'update', 'tag'].forEach((key) => {
      const field = fields[key];
      if (field?.value) labels.push(`${key[0].toUpperCase()}${key.slice(1)}: ${field.options[field.selectedIndex]?.text || field.value}`);
    });
    tokens.replaceChildren(...labels.map((label) => {
      const token = document.createElement('span'); token.className = 'filter-token'; token.textContent = label; return token;
    }));
    resultCount.textContent = `${matches.length} of ${trackerRows.length} software shown`;
    summary.hidden = labels.length === 0;
  }
  function renderTrackerPage(reset = false) {
    if (reset) trackerPage = 1;
    applyTrackerSort();
    const matches = filteredTrackerRows();
    const pages = Math.max(1, Math.ceil(matches.length / trackerPageSize));
    trackerPage = Math.min(Math.max(1, trackerPage), pages);
    sessionStorage.setItem(storageKeys.page, String(trackerPage));
    const start = (trackerPage - 1) * trackerPageSize;
    const end = Math.min(start + trackerPageSize, matches.length);
    const shown = new Set(matches.slice(start, end));
    trackerRows.forEach((row) => { row.hidden = !shown.has(row); });
    document.getElementById('tracker-page-info').textContent = matches.length ? `Showing ${start + 1}–${end} of ${matches.length} matching software` : 'No matching software';
    document.getElementById('tracker-page-label').textContent = `Page ${trackerPage} of ${pages}`;
    document.getElementById('tracker-first').disabled = trackerPage <= 1;
    document.getElementById('tracker-prev').disabled = trackerPage <= 1;
    document.getElementById('tracker-next').disabled = trackerPage >= pages;
    document.getElementById('tracker-last').disabled = trackerPage >= pages;
    updateFilterSummary(matches);
    updateSelectedCount();
  }
  function filterTrackers() { renderTrackerPage(true); }

  window.toggleSelectAll = function toggleSelectAll(checked) { visibleCheckboxes().forEach((box) => { box.checked = checked; }); updateSelectedCount(); };
  window.updateSelectedCount = function updateSelectedCount() {
    const all = Array.from(document.querySelectorAll('.tracker-checkbox'));
    const selected = all.filter((box) => box.checked);
    const visible = visibleCheckboxes();
    const selectedVisible = visible.filter((box) => box.checked);
    const count = document.getElementById('selected-count');
    if (count) count.textContent = `${selected.length} selected`;
    const apply = document.getElementById('bulk-apply');
    const action = document.getElementById('bulk-action');
    if (apply) apply.disabled = selected.length === 0 || !action?.value;
    const selectAll = document.getElementById('select-all-trackers');
    if (selectAll) {
      selectAll.checked = visible.length > 0 && selectedVisible.length === visible.length;
      selectAll.indeterminate = selectedVisible.length > 0 && selectedVisible.length < visible.length;
    }
  };
  window.updateBulkControls = function updateBulkControls() {
    const action = document.getElementById('bulk-action')?.value || '';
    const refresh = document.getElementById('bulk-refresh-hours');
    if (refresh) refresh.hidden = action !== 'refresh';
    updateSelectedCount();
  };
  window.confirmBulkAction = function confirmBulkAction() {
    const action = document.getElementById('bulk-action')?.value || '';
    const count = document.querySelectorAll('.tracker-checkbox:checked').length;
    if (!action || !count) return false;
    return action !== 'delete' || confirm(`Delete ${count} selected tracker(s) and their history?`);
  };

  function setDensity(density, announce = false) {
    dashboardDensity = density === 'compact' ? 'compact' : 'comfortable';
    document.body.classList.toggle('dashboard-compact', dashboardDensity === 'compact');
    document.querySelectorAll('[data-density]').forEach((button) => button.classList.toggle('active', button.dataset.density === dashboardDensity));
    localStorage.setItem(storageKeys.density, dashboardDensity);
    if (announce) window.SRR?.notify(`Dashboard rows are now ${dashboardDensity}.`, 'info');
  }
  function setPreset(preset, resetPage = true) {
    activePreset = ['all', 'updates', 'attention', 'paused'].includes(preset) ? preset : 'all';
    document.querySelectorAll('[data-view-preset]').forEach((button) => button.classList.toggle('active', button.dataset.viewPreset === activePreset));
    renderTrackerPage(resetPage);
  }
  function updatePresetCounts() {
    ['all', 'updates', 'attention', 'paused'].forEach((preset) => {
      const count = trackerRows.filter((row) => matchesPreset(row, preset)).length;
      const target = document.querySelector(`[data-view-count="${preset}"]`);
      if (target) target.textContent = count;
    });
  }
  function currentViewState() {
    return {
      preset: activePreset,
      filter: fields.filter?.value || '', machine: fields.machine?.value || '',
      connectivity: fields.connectivity?.value || '', update: fields.update?.value || '', tag: fields.tag?.value || '',
      sortKey: trackerSort.key, sortDirection: trackerSort.direction, pageSize: trackerPageSize, density: dashboardDensity,
    };
  }
  function applyViewState(state, announce = false) {
    activePreset = state.preset || 'all';
    Object.keys(fields).forEach((key) => { if (fields[key] && typeof state[key] === 'string') fields[key].value = state[key]; });
    trackerSort.key = state.sortKey || 'name'; trackerSort.direction = state.sortDirection || 'asc';
    trackerPageSize = [10,25,50,100,200].includes(Number(state.pageSize)) ? Number(state.pageSize) : trackerPageSize;
    const pageSize = document.getElementById('tracker-page-size'); if (pageSize) pageSize.value = String(trackerPageSize);
    const activeButton = document.querySelector(`.tracker-sort-header[data-sort="${trackerSort.key}"]`); trackerSort.type = activeButton?.dataset.type || 'text';
    setDensity(state.density || dashboardDensity);
    document.querySelectorAll('[data-view-preset]').forEach((button) => button.classList.toggle('active', button.dataset.viewPreset === activePreset));
    renderTrackerPage(true);
    if (announce) window.SRR?.notify('Saved dashboard view applied.', 'success');
  }
  function savedViews() { return readJson(storageKeys.views, {}); }
  function renderSavedViews(selected = '') {
    const select = document.getElementById('saved-dashboard-view'); if (!select) return;
    const views = savedViews(); select.innerHTML = '<option value="">Saved views…</option>';
    Object.keys(views).sort(collator.compare).forEach((name) => { const option = document.createElement('option'); option.value = name; option.textContent = name; select.append(option); });
    select.value = selected in views ? selected : '';
    document.getElementById('delete-dashboard-view').disabled = !select.value;
  }
  function resetDashboard() {
    Object.values(fields).forEach((field) => { if (field) field.value = ''; });
    activePreset = 'all'; trackerSort = { key: 'name', direction: 'asc', type: 'text' }; trackerPageSize = 25;
    document.getElementById('tracker-page-size').value = '25';
    document.documentElement.style.removeProperty('--tracker-software-width');
    ['software','installed','current','refresh','checked'].forEach((key) => document.documentElement.style.removeProperty(`--tracker-${key}-width`));
    localStorage.removeItem(storageKeys.columns); localStorage.removeItem(storageKeys.sortKey); localStorage.removeItem(storageKeys.sortDirection); localStorage.removeItem(storageKeys.pageSize);
    setDensity('comfortable'); setPreset('all'); renderSavedViews(); window.SRR?.notify('Dashboard filters and layout reset.', 'success');
  }

  function initialiseColumnResizers() {
    const root = document.documentElement;
    const widths = readJson(storageKeys.columns, {});
    Object.entries(widths).forEach(([key, value]) => root.style.setProperty(`--tracker-${key}-width`, `${value}px`));
    document.querySelectorAll('.column-resizer').forEach((handle) => {
      handle.addEventListener('pointerdown', (event) => {
        event.preventDefault(); event.stopPropagation();
        const key = handle.dataset.column; const property = `--tracker-${key}-width`;
        const computed = parseFloat(getComputedStyle(root).getPropertyValue(property)) || handle.parentElement.getBoundingClientRect().width;
        const startX = event.clientX; const minimum = key === 'software' ? 220 : 90;
        document.body.classList.add('resizing-columns');
        const move = (moveEvent) => { const width = Math.max(minimum, computed + moveEvent.clientX - startX); root.style.setProperty(property, `${width}px`); widths[key] = Math.round(width); };
        const up = () => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.body.classList.remove('resizing-columns'); localStorage.setItem(storageKeys.columns, JSON.stringify(widths)); };
        document.addEventListener('pointermove', move); document.addEventListener('pointerup', up);
      });
    });
  }
  function saveDashboardState() {
    const state = { ...currentViewState(), page: trackerPage, scrollY: window.scrollY };
    sessionStorage.setItem(storageKeys.state, JSON.stringify(state));
    sessionStorage.setItem(storageKeys.page, String(trackerPage));
  }
  function restoreDashboardState() {
    let state = {}; try { state = JSON.parse(sessionStorage.getItem(storageKeys.state) || '{}'); } catch (error) {}
    if (Number.isFinite(Number(state.page)) && Number(state.page) > 0) trackerPage = Number(state.page);
    applyViewState(state);
    return Number(state.scrollY) || 0;
  }

  document.querySelectorAll('.tracker-sort-header').forEach((button) => button.addEventListener('click', (event) => {
    if (event.target.classList.contains('column-resizer')) return;
    const key = button.dataset.sort; trackerSort.type = button.dataset.type || 'text';
    if (trackerSort.key === key) trackerSort.direction = trackerSort.direction === 'asc' ? 'desc' : 'asc';
    else { trackerSort.key = key; trackerSort.direction = 'asc'; }
    renderTrackerPage(true);
  }));
  document.querySelectorAll('[data-view-preset]').forEach((button) => button.addEventListener('click', () => setPreset(button.dataset.viewPreset)));
  document.querySelectorAll('[data-density]').forEach((button) => button.addEventListener('click', () => setDensity(button.dataset.density, true)));
  const size = document.getElementById('tracker-page-size'); size.value = String(trackerPageSize);
  size.addEventListener('change', () => { trackerPageSize = Number(size.value); localStorage.setItem(storageKeys.pageSize, String(trackerPageSize)); renderTrackerPage(true); });
  fields.filter?.addEventListener('input', filterTrackers);
  ['machine', 'connectivity', 'update', 'tag'].forEach((key) => fields[key]?.addEventListener('change', filterTrackers));
  document.getElementById('tracker-first').addEventListener('click', () => { trackerPage = 1; renderTrackerPage(); });
  document.getElementById('tracker-prev').addEventListener('click', () => { trackerPage -= 1; renderTrackerPage(); });
  document.getElementById('tracker-next').addEventListener('click', () => { trackerPage += 1; renderTrackerPage(); });
  document.getElementById('tracker-last').addEventListener('click', () => { trackerPage = Math.ceil(filteredTrackerRows().length / trackerPageSize) || 1; renderTrackerPage(); });
  document.getElementById('saved-dashboard-view')?.addEventListener('change', (event) => {
    const name = event.target.value; document.getElementById('delete-dashboard-view').disabled = !name;
    if (name) applyViewState(savedViews()[name], true);
  });
  document.getElementById('save-dashboard-view')?.addEventListener('click', () => {
    const suggested = document.getElementById('saved-dashboard-view')?.value || '';
    const name = prompt('Name this dashboard view:', suggested); if (!name?.trim()) return;
    const views = savedViews(); views[name.trim()] = currentViewState(); localStorage.setItem(storageKeys.views, JSON.stringify(views)); renderSavedViews(name.trim()); window.SRR?.notify(`Saved view “${name.trim()}”.`, 'success');
  });
  document.getElementById('delete-dashboard-view')?.addEventListener('click', () => {
    const select = document.getElementById('saved-dashboard-view'); const name = select?.value; if (!name) return;
    const views = savedViews(); delete views[name]; localStorage.setItem(storageKeys.views, JSON.stringify(views)); renderSavedViews(); window.SRR?.notify(`Deleted view “${name}”.`, 'info');
  });
  document.getElementById('reset-dashboard-view')?.addEventListener('click', resetDashboard);
  document.querySelectorAll('form').forEach((form) => form.addEventListener('submit', saveDashboardState));
  document.querySelectorAll('a[data-preserve-dashboard-state], .tracker-actions a').forEach((link) => link.addEventListener('click', saveDashboardState));
  window.addEventListener('beforeunload', saveDashboardState);

  window.SRR = Object.assign(window.SRR || {}, {
    focusDashboardSearch() { fields.filter?.focus(); fields.filter?.scrollIntoView({ block: 'center' }); },
    toggleDashboardDensity() { setDensity(dashboardDensity === 'compact' ? 'comfortable' : 'compact', true); },
  });

  initialiseColumnResizers(); updatePresetCounts(); renderSavedViews(); setDensity(dashboardDensity);
  const restoredScrollY = restoreDashboardState();
  const commandParams = new URLSearchParams(window.location.search);
  if (commandParams.get('density') === 'toggle') setDensity(dashboardDensity === 'compact' ? 'comfortable' : 'compact', true);
  if (commandParams.get('focus') === 'search') requestAnimationFrame(() => window.SRR?.focusDashboardSearch?.());
  if (commandParams.has('density') || commandParams.has('focus')) history.replaceState(null, '', window.location.pathname);

  document.getElementById('bulk-form')?.addEventListener('submit', (event) => { if (!window.confirmBulkAction()) event.preventDefault(); });
  document.getElementById('select-all-trackers')?.addEventListener('change', (event) => window.toggleSelectAll(event.target.checked));
  document.getElementById('bulk-action')?.addEventListener('change', () => window.updateBulkControls());
  document.querySelectorAll('.tracker-checkbox').forEach((box) => box.addEventListener('change', () => window.updateSelectedCount()));
  requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: restoredScrollY, behavior: 'instant' })));
})();
