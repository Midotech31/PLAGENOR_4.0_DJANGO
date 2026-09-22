(() => {
  'use strict';
  document.querySelectorAll('[data-position-source]').forEach(source => {
    const form = source.closest('form[data-position-endpoint]');
    const target = document.getElementById(source.dataset.positionSource);
    if (!form || !target) return;
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.className = 'erp-muted';
    target.insertAdjacentElement('afterend', status);
    let controller;
    source.addEventListener('change', async () => {
      if (controller) controller.abort();
      controller = new AbortController();
      target.replaceChildren(new Option(form.dataset.positionEmpty, ''));
      target.required = false;
      if (!source.value) { status.textContent = ''; return; }
      status.textContent = form.dataset.positionLoading;
      target.disabled = true;
      const url = new URL(form.dataset.positionEndpoint, window.location.origin);
      url.searchParams.set('location', source.value);
      try {
        const response = await fetch(url, {credentials: 'same-origin', signal: controller.signal});
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('positions');
        const result = await response.json();
        result.positions.forEach(position => {
          let label = position.label;
          if (position.occupied) label += ' — ' + form.dataset.positionOccupied;
          else if (position.reserved) label += ' — ' + form.dataset.positionReserved;
          const option = new Option(label, position.id);
          option.disabled = position.occupied || position.reserved;
          target.add(option);
        });
        target.required = result.grid_required;
        status.textContent = '';
      } catch (error) {
        if (error.name !== 'AbortError') status.textContent = form.dataset.positionError;
      } finally {
        target.disabled = false;
      }
    });
  });
})();
