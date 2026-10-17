(() => {
  const input = document.getElementById('notification-filter');
  const rows = [...document.querySelectorAll('.software-notification-row')];
  const selectAll = document.getElementById('select-all-notification-trackers');
  const count = document.getElementById('notification-selected-count');
  const empty = document.getElementById('notification-empty');
  const softwareForm = document.getElementById('software-notification-form');
  const defaultsForm = document.getElementById('notification-defaults-form');
  if (!input || !selectAll || !count || !softwareForm || !defaultsForm) return;

  const filterStorageKey = 'software-release-radar.notifications.filter';
  const notify = (message, type = 'info') => {
    if (window.SRR && typeof window.SRR.notify === 'function') {
      window.SRR.notify(message, type);
    } else if (type === 'error') {
      console.error(message);
    }
  };
  const visibleRows = () => rows.filter(row => !row.hidden);
  const visibleBoxes = () => visibleRows().map(row => row.querySelector('.notification-tracker-checkbox'));
  const selectedRows = () => rows.filter(row => row.querySelector('.notification-tracker-checkbox').checked);

  const updateSelection = () => {
    const selected = selectedRows().length;
    count.textContent = `${selected} selected`;
    const boxes = visibleBoxes();
    selectAll.checked = boxes.length > 0 && boxes.every(box => box.checked);
    selectAll.indeterminate = boxes.some(box => box.checked) && !selectAll.checked;
  };

  const storeFilter = () => {
    try {
      window.sessionStorage.setItem(filterStorageKey, input.value || '');
    } catch (error) {
      // Storage can be unavailable in hardened browser modes. Filtering still works.
    }
  };

  const filter = () => {
    const query = (input.value || '').trim().toLowerCase();
    rows.forEach(row => { row.hidden = Boolean(query) && !row.dataset.notificationSearch.includes(query); });
    empty.hidden = visibleRows().length !== 0 || rows.length === 0;
    storeFilter();
    updateSelection();
  };

  const updateNotificationState = () => {
    const systemEnabled = defaultsForm.dataset.systemEnabled === '1';
    const defaultEnabled = defaultsForm.dataset.defaultEnabled === '1';
    const preferenceCounts = { inherit: 0, on: 0, off: 0 };

    rows.forEach(row => {
      const select = row.querySelector('[data-notification-mode]');
      const badge = row.querySelector('[data-notification-effective]');
      if (!select || !badge) return;
      const mode = select.value;
      if (Object.prototype.hasOwnProperty.call(preferenceCounts, mode)) preferenceCounts[mode] += 1;

      let state = 'off';
      let label = 'Muted';
      if (!systemEnabled) {
        state = 'paused';
        label = 'System paused';
      } else if (mode === 'on' || (mode === 'inherit' && defaultEnabled)) {
        state = 'on';
        label = 'Will notify';
      }
      badge.className = `status-badge state-${state}`;
      badge.textContent = label;
    });

    Object.entries(preferenceCounts).forEach(([mode, value]) => {
      const metric = document.querySelector(`[data-notification-count="${mode}"]`);
      if (metric) metric.textContent = String(value);
    });

    const systemMetric = document.querySelector('[data-notification-system-state]');
    if (systemMetric) {
      systemMetric.textContent = systemEnabled ? 'On' : 'Paused';
      systemMetric.className = `metric-state ${systemEnabled ? 'state-on' : 'state-paused'}`;
    }
    const defaultMetric = document.querySelector('[data-notification-default-state]');
    if (defaultMetric) {
      defaultMetric.textContent = defaultEnabled ? 'On' : 'Muted';
      defaultMetric.className = `metric-state ${defaultEnabled ? 'state-on' : 'state-off'}`;
    }
  };

  const postNotificationForm = async (formData) => {
    const response = await fetch(window.location.href, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!response.ok) throw new Error(`Notification save failed with HTTP ${response.status}.`);
    const finalUrl = new URL(response.url, window.location.href);
    if (finalUrl.pathname !== window.location.pathname) {
      window.location.assign(response.url);
      throw new Error('The notification session changed before the preference was saved.');
    }
  };

  const setFormBusy = (form, busy) => {
    form.toggleAttribute('aria-busy', busy);
    form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = busy; });
  };

  try {
    const storedFilter = window.sessionStorage.getItem(filterStorageKey);
    if (storedFilter) input.value = storedFilter;
  } catch (error) {
    // Ignore unavailable session storage.
  }

  input.addEventListener('input', filter);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') event.preventDefault();
  });
  selectAll.addEventListener('change', () => {
    visibleBoxes().forEach(box => { box.checked = selectAll.checked; });
    updateSelection();
  });
  rows.forEach(row => row.querySelector('.notification-tracker-checkbox').addEventListener('change', updateSelection));

  rows.forEach(row => {
    const select = row.querySelector('[data-notification-mode]');
    if (!select) return;
    select.addEventListener('change', async () => {
      const savedMode = select.dataset.savedMode || 'inherit';
      const formData = new FormData();
      formData.set('csrf_token', softwareForm.querySelector('input[name="csrf_token"]').value);
      formData.set('action', 'save_software');
      formData.set(`mode_${row.dataset.trackerId}`, select.value);
      select.disabled = true;
      try {
        await postNotificationForm(formData);
        select.dataset.savedMode = select.value;
        updateNotificationState();
        notify('Notification preference saved.', 'success');
      } catch (error) {
        select.value = savedMode;
        updateNotificationState();
        notify(error.message || 'Could not save the notification preference.', 'error');
      } finally {
        select.disabled = false;
      }
    });
  });

  softwareForm.addEventListener('submit', async event => {
    event.preventDefault();
    const submitter = event.submitter;
    const action = submitter && submitter.value ? submitter.value : 'save_software';
    const selected = selectedRows();
    if (action === 'bulk_software' && selected.length === 0) {
      notify('Select at least one software tracker.', 'error');
      return;
    }

    const formData = new FormData(softwareForm);
    formData.set('action', action);
    setFormBusy(softwareForm, true);
    try {
      await postNotificationForm(formData);
      if (action === 'bulk_software') {
        const mode = document.getElementById('notification-bulk-mode').value;
        selected.forEach(row => {
          const select = row.querySelector('[data-notification-mode]');
          const checkbox = row.querySelector('.notification-tracker-checkbox');
          if (select) {
            select.value = mode;
            select.dataset.savedMode = mode;
          }
          if (checkbox) checkbox.checked = false;
        });
        notify(`Updated ${selected.length} software notification preference${selected.length === 1 ? '' : 's'}.`, 'success');
      } else {
        rows.forEach(row => {
          const select = row.querySelector('[data-notification-mode]');
          if (select) select.dataset.savedMode = select.value;
        });
        notify('All software notification preferences saved.', 'success');
      }
      updateNotificationState();
      updateSelection();
    } catch (error) {
      notify(error.message || 'Could not save software notification preferences.', 'error');
    } finally {
      setFormBusy(softwareForm, false);
    }
  });

  defaultsForm.addEventListener('submit', async event => {
    event.preventDefault();
    const formData = new FormData(defaultsForm);
    setFormBusy(defaultsForm, true);
    try {
      await postNotificationForm(formData);
      const systemControl = defaultsForm.querySelector('input[name="system_notifications_enabled"]');
      const defaultControl = defaultsForm.querySelector('input[name="notifications_enabled"]');
      if (systemControl) defaultsForm.dataset.systemEnabled = systemControl.checked ? '1' : '0';
      if (defaultControl) defaultsForm.dataset.defaultEnabled = defaultControl.checked ? '1' : '0';
      updateNotificationState();
      notify('Global notification defaults saved.', 'success');
    } catch (error) {
      notify(error.message || 'Could not save global notification defaults.', 'error');
    } finally {
      setFormBusy(defaultsForm, false);
    }
  });

  filter();
  updateNotificationState();
})();
