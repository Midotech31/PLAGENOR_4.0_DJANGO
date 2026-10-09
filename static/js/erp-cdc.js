'use strict';

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-cdc-select]');
  if (!button) return;
  const checked = button.dataset.cdcSelect === 'all';
  button.closest('form').querySelectorAll('input[name="selections"]').forEach((input) => {
    input.checked = checked;
  });
});

document.querySelectorAll('form[data-cdc-progress]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.cdcBusy === 'true') {
      event.preventDefault();
      return;
    }
    form.dataset.cdcBusy = 'true';
    form.setAttribute('aria-busy', 'true');
    const button = event.submitter;
    if (button) {
      // Disabled submitters are omitted from the POST; retain the chosen action.
      if (button.name) {
        const action = document.createElement('input');
        action.type = 'hidden';
        action.name = button.name;
        action.value = button.value;
        action.dataset.cdcAction = 'true';
        form.append(action);
      }
      button.dataset.cdcOriginalLabel = button.textContent;
      button.disabled = true;
    }
    const status = document.createElement('p');
    status.dataset.cdcStatus = 'true';
    status.setAttribute('role', 'status');
    status.textContent = form.dataset.cdcProgress;
    form.append(status);
  });
});

window.addEventListener('pageshow', () => {
  document.querySelectorAll('form[data-cdc-progress]').forEach((form) => {
    form.dataset.cdcBusy = 'false';
    form.removeAttribute('aria-busy');
    form.querySelectorAll('[data-cdc-status], [data-cdc-action]').forEach((node) => node.remove());
    form.querySelectorAll('[data-cdc-original-label]').forEach((button) => {
      button.disabled = false;
      button.textContent = button.dataset.cdcOriginalLabel;
      delete button.dataset.cdcOriginalLabel;
    });
  });
});
