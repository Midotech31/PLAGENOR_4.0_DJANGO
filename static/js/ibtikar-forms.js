(() => {
  'use strict';
  const editor = document.querySelector('[data-ibk-editor]');
  if (!editor) return;
  const t = value => window.gettext ? window.gettext(value) : value;
  const fields = group => [...group.querySelectorAll('[data-ibk-field]')];
  const controls = field => [...field.querySelectorAll('input:not([data-ibk-retained]),select,textarea')];
  const read = group => Object.fromEntries(fields(group).map(field => {
    const items = controls(field), first = items[0];
    let value = first?.value ?? '';
    if (items.some(x => x.type === 'checkbox')) value = items.filter(x => x.checked).map(x => x.value);
    if (first?.tagName === 'SELECT' && first.multiple) value = [...first.selectedOptions].map(x => x.value);
    return [field.dataset.ibkField, value];
  }));
  const groups = () => [...editor.querySelectorAll('[data-ibk-group]')];
  const sampleGroups = () => groups().filter(x => x.dataset.ibkGroup === 'sample' && x.dataset.deleted !== 'true');
  const parameters = () => {
    const group = editor.querySelector('[data-ibk-group="parameters"]');
    return group ? read(group) : {};
  };
  function matches(rule, values, active, params, samples) {
    if (!rule || !Object.keys(rule).length) return true;
    if (rule.any) return rule.any.some(x => matches(x, values, active, params, samples));
    if (rule.all) return rule.all.every(x => matches(x, values, active, params, samples));
    if (rule.any_row) return samples.some(row => matches(rule.any_row, row, null, params, samples));
    const source = rule.scope === 'parameters' ? params : values;
    if (rule.scope !== 'parameters' && active && !active.has(rule.field)) return false;
    const value = source[rule.field];
    return (Array.isArray(value) ? value : [value]).some(x => (rule.in || []).includes(x));
  }
  const rules = JSON.parse(document.getElementById('ibk-form-rules')?.textContent || '[]');
  const language = document.documentElement.lang.split('-')[0];
  const localized = value => typeof value === 'object' ? value[language] || value.fr : value;
  const applicable = group => Object.fromEntries(fields(group).filter(f => !f.hidden).map(f => [f.dataset.ibkField, read(group)[f.dataset.ibkField]]));
  const empty = value => value === '' || value == null || (Array.isArray(value) && !value.length);
  function preserveInactive(entry, show) {
    entry.querySelectorAll('[data-ibk-retained]').forEach(x => x.remove());
    for (const input of controls(entry)) {
      input.disabled = !show;
      if (show || input.type === 'file' || !input.name) continue;
      const values = input.type === 'checkbox' ? (input.checked ? [input.value] : []) : input.multiple ? [...input.selectedOptions].map(x => x.value) : [input.value];
      for (const value of values) {
        const mirror = document.createElement('input');
        mirror.type = 'hidden'; mirror.name = input.name; mirror.value = value;
        mirror.dataset.ibkRetained = 'true'; entry.append(mirror);
      }
    }
  }
  function checkRules(group, values, params) {
    const warnings = [];
    const invalid = (field, message) => {
      const entry = fields(group).find(x => x.dataset.ibkField === field && !x.hidden);
      if (!entry) return;
      controls(entry)[0]?.setCustomValidity(message); warnings.push(message);
    };
    for (const rule of rules) {
      if (!matches(rule.when, values, null, params, [])) continue;
      if (rule.kind === 'required_value' && !empty(values[rule.field]) && values[rule.field] !== rule.value) invalid(rule.field, localized(rule.message));
      if (rule.kind === 'risk_consistency' && values.origin === 'clinical' && values.risk_status === 'standard') invalid('risk_status', t('Une origine clinique ne peut pas être déclarée standard.'));
      if (rule.kind === 'fill_ratio' && !empty(values.fill_volume_ml) && Number(values.container_volume_ml) > 0 && Number(values.fill_volume_ml) / Number(values.container_volume_ml) > Number(rule.maximum)) invalid('fill_volume_ml', t('Le remplissage dépasse 50 % du volume nominal du récipient.'));
      if (rule.kind === 'minimum_quantity' && values.sample_type === rule.sample_type && !empty(values.quantity)) {
        const factor = {g:{g:1,mg:0.001},mL:{mL:1,uL:0.001}}[rule.unit]?.[values.quantity_unit];
        if (factor == null && !empty(values.quantity_unit)) invalid('quantity_unit', t('Cette unité ne permet pas de vérifier la quantité minimale requise.'));
        else if (factor != null && Number(values.quantity) * factor < Number(rule.minimum)) invalid('quantity', t('Quantité minimale requise') + ` : ${rule.minimum} ${rule.unit}`);
      }
      if (rule.kind === 'solvent_review' && Number(values[rule.field]) >= Number(rule.threshold)) warnings.push(localized(rule.message));
    }
    const note = group.querySelector('.ibk-row-warning');
    if (note) note.textContent = [...new Set(warnings)].join(' ');
  }
  let dirty = false, timer, controller;
  function evaluate() {
    let params = parameters(), samples = sampleGroups().map(applicable);
    for (const group of groups()) {
      if (group.dataset.deleted === 'true') continue;
      const entries = fields(group), values = read(group);
      let active = new Set(entries.filter(x => x.dataset.ibkWhen === '{}').map(x => x.dataset.ibkField));
      for (let i = 0; i <= entries.length; i++) {
        const next = new Set(entries.filter(x => matches(JSON.parse(x.dataset.ibkWhen || '{}'), values, active, params, samples)).map(x => x.dataset.ibkField));
        if (next.size === active.size && [...next].every(x => active.has(x))) break;
        active = next;
      }
      for (const entry of entries) {
        const show = active.has(entry.dataset.ibkField);
        entry.hidden = !show;
        preserveInactive(entry, show);
        const items = controls(entry), checkboxGroup = items.length > 1 && items.every(x => x.type === 'checkbox');
        for (const input of items) { input.setCustomValidity(''); input.required = show && entry.dataset.ibkRequired === 'true' && !checkboxGroup && (input.type !== 'file' || entry.dataset.filePresent !== 'true'); }
        if (checkboxGroup) {
          items.forEach(input => input.setCustomValidity(''));
          const chosen = items.filter(x => x.checked).map(x => x.value);
          if (show && chosen.length > 1 && JSON.parse(entry.dataset.ibkExclusive || '[]').some(x => chosen.includes(x))) items[0]?.setCustomValidity(t('Ce choix ne peut pas être combiné avec une autre option.'));
          if (show && entry.dataset.ibkRequired === 'true' && !items.some(x => x.checked)) items[0]?.setCustomValidity(t('Sélectionnez au moins une option.'));
        }
      }
      if (group.dataset.ibkGroup === 'parameters') params = applicable(group);
      if (group.dataset.ibkGroup === 'sample') checkRules(group, applicable(group), params);
      if (group.dataset.ibkGroup === 'sample') samples = sampleGroups().map(applicable);
      const sequence = values.sequence;
      const computed = group.querySelector('[data-primer-computed]');
      if (computed && typeof sequence === 'string' && sequence) {
        const normalized = sequence.replace(/\s/g, '').toUpperCase();
        const gc = /^[ACGT]+$/.test(normalized) ? (100 * [...normalized].filter(x => 'GC'.includes(x)).length / normalized.length).toFixed(2) + '%' : t('Indéterminé');
        computed.textContent = `${t('Taille')} : ${normalized.length} nt · GC : ${gc}`;
      } else if (computed) computed.textContent = '';
    }
    sampleGroups().forEach((row, i) => { row.querySelector('[data-row-number]').textContent = i + 1; });
    document.getElementById('ibk-row-count').textContent = `(${sampleGroups().length})`;
  }
  async function estimate() {
    const output = document.getElementById('ibk-estimate-value');
    if (!output || editor.dataset.priceVisible !== 'true') return;
    controller?.abort(); controller = new AbortController();
    const data = new FormData(editor);
    for (const [key, value] of [...data]) if (value instanceof File) data.delete(key);
    try {
      const response = await fetch(editor.dataset.estimateUrl, {method:'POST',body:data,signal:controller.signal,credentials:'same-origin'});
      if (!response.ok) throw new Error('estimate');
      const result = await response.json();
      if (!result.visible) { output.textContent = t('Estimation non publiée.'); return; }
      output.textContent = result.total !== null ? `${result.total} DZD` : result.status === 'incomplete' ? t('Complétez les paramètres et les échantillons pour obtenir une estimation.') : t('Tarification à valider par PLAGENOR — aucun montant total n’est encore arrêté.');
    } catch (error) { if (error.name !== 'AbortError') output.textContent = t('Estimation temporairement indisponible.'); }
  }
  editor.addEventListener('input', () => { dirty = true; evaluate(); clearTimeout(timer); timer = setTimeout(estimate, 500); });
  editor.addEventListener('change', () => { dirty = true; evaluate(); clearTimeout(timer); timer = setTimeout(estimate, 300); });
  document.getElementById('ibk-add-sample').addEventListener('click', () => {
    const total = editor.querySelector('[name="samples-TOTAL_FORMS"]'), maximum = Number(editor.querySelector('[name="samples-MAX_NUM_FORMS"]').value);
    if (Number(total.value) >= maximum) { alert(t('La limite technique de lignes est atteinte. Contactez PLAGENOR pour un dépôt plus volumineux.')); return; }
    const fragment = document.createElement('template');
    fragment.innerHTML = document.getElementById('ibk-empty-sample').innerHTML.replace(/__prefix__/g, total.value);
    document.getElementById('ibk-samples').append(fragment.content); total.value = Number(total.value) + 1;
    dirty = true; evaluate();
  });
  editor.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-sample]');
    if (!button) return;
    if (!confirm(t('Retirer cette ligne de la demande ?'))) return;
    const group = button.closest('[data-ibk-group="sample"]');
    group.querySelector('[name$="-DELETE"]').checked = true;
    group.dataset.deleted = 'true'; group.hidden = true;
    controls(group).forEach(x => { x.required = false; x.setCustomValidity(''); });
    dirty = true; evaluate(); estimate();
  });
  editor.addEventListener('submit', () => { dirty = false; });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  evaluate();
  estimate();
  if (document.querySelector('.ibk-errors')) document.querySelector('.ibk-errors').focus();
})();
