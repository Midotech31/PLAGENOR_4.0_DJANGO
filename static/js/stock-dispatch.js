'use strict';
const stockAdd = document.getElementById('dispatch-add');
if (stockAdd) {
  const form = stockAdd.closest('form');
  const timers = new WeakMap();
  const requests = new WeakMap();
  form.addEventListener('input', event => {
    const input = event.target;
    if (!input.matches('[data-container-search]')) return;
    input.setCustomValidity('');
    clearTimeout(timers.get(input));
    const previous = requests.get(input);
    if (previous) previous.abort();
    timers.set(input, setTimeout(async () => {
      const controller = new AbortController();
      requests.set(input, controller);
      const select = input.closest('fieldset').querySelector('select[name$="-container"]');
      try {
        const url = new URL(form.dataset.sourcesUrl, window.location.origin);
        url.searchParams.set('q', input.value);
        const response = await fetch(url, {signal:controller.signal, credentials:'same-origin'});
        if (!response.ok) throw new Error('search');
        const data = await response.json();
        const selected = select.selectedOptions[0]?.cloneNode(true);
        select.replaceChildren(new Option('---------', ''));
        for (const row of data.results) {
          const option = new Option(row.label, row.id);
          option.dataset.version = String(row.version);
          option.dataset.unit = row.unit;
          select.append(option);
        }
        if (selected?.value && !Array.from(select.options).some(option => option.value === selected.value)) select.append(selected);
        if (selected) select.value = selected.value;
      } catch (error) {
        if (error.name !== 'AbortError') input.setCustomValidity(form.dataset.searchError);
      }
    }, 250));
  });
  form.addEventListener('change', event => {
    const select = event.target;
    if (!select.matches('select[name$="-container"]')) return;
    const fieldset = select.closest('fieldset');
    const option = select.selectedOptions[0];
    fieldset.querySelector('input[name$="-expected"]').value = option?.dataset.version || '';
    const unit = fieldset.querySelector('select[name$="-unit"]');
    if (option?.dataset.unit) unit.value = option.dataset.unit;
  });
  stockAdd.addEventListener('click', () => {
    const total = document.getElementById('id_lines-TOTAL_FORMS');
    const count = Number(total.value);
    if (count >= 100) return;
    const section = document.createElement('div');
    section.innerHTML = document.getElementById('dispatch-empty').innerHTML.replaceAll('__prefix__', String(count));
    document.getElementById('dispatch-lines').append(...section.childNodes);
    total.value = String(count + 1);
    stockAdd.disabled = count + 1 >= 100;
  });
}
