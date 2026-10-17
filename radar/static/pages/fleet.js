(() => {
  const input = document.getElementById('fleet-filter');
  const cards = [...document.querySelectorAll('.fleet-card')];
  const summary = document.getElementById('fleet-results-summary');
  const empty = document.getElementById('fleet-empty');
  function apply() {
    const query = (input.value || '').trim().toLowerCase();
    let visibleMachines = 0;
    let visibleServices = 0;
    cards.forEach(card => {
      const machineMatch = !query || card.dataset.machineSearch.includes(query);
      let cardServices = 0;
      card.querySelectorAll('.fleet-service').forEach(service => {
        const match = machineMatch || !query || service.dataset.serviceSearch.includes(query);
        service.hidden = !match;
        if (match) cardServices += 1;
      });
      card.hidden = cardServices === 0;
      if (!card.hidden) {
        visibleMachines += 1;
        visibleServices += cardServices;
      }
    });
    summary.textContent = `${visibleMachines} machine${visibleMachines === 1 ? '' : 's'} · ${visibleServices} service${visibleServices === 1 ? '' : 's'}`;
    empty.hidden = visibleMachines !== 0 || cards.length === 0;
  }
  input.addEventListener('input', apply);
  apply();
})();
