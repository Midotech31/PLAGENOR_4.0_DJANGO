(function () {
    'use strict';
    const source = document.getElementById('guest-saved-values');
    const saved = source ? JSON.parse(source.textContent) : {};
    const form = document.querySelector('form[action="/guest/submit/"]') || document.querySelector('input[name="guest_email"]')?.form;
    if (!form) return;
    const service = form.elements.namedItem('service_id');
    const orgType = form.elements.namedItem('organization_type');
    const orgOther = document.getElementById('guest-org-other-group');
    let restored = false;
    function fill(scope) {
        scope.querySelectorAll('input[name], select[name], textarea[name]').forEach(function (field) {
            const values = saved[field.name];
            if (!values || field.type === 'file' || field.name === 'csrfmiddlewaretoken') return;
            if (field.type === 'checkbox' || field.type === 'radio') field.checked = values.includes(field.value);
            else field.value = values[values.length - 1];
        });
    }
    function organization() {
        if (orgOther) orgOther.style.display = orgType && orgType.value === 'autre' ? '' : 'none';
    }
    document.addEventListener('serviceFormLoaded', function (event) {
        if (restored || !saved.service_id || event.detail.serviceId !== saved.service_id[0]) return;
        const target = document.getElementById('dynamic-service-form');
        const body = target.querySelector('#sample-table-body');
        if (body && body.firstElementChild) {
            const indices = Array.from(new Set(Object.keys(saved).map(function (key) {
                const match = /^sample_([0-9]+)_/.exec(key);
                return match ? match[1] : null;
            }).filter(function (key) { return key !== null; }))).slice(0, 200);
            if (indices.length) {
                const model = body.firstElementChild.cloneNode(true);
                body.replaceChildren();
                indices.forEach(function (index) {
                    const row = model.cloneNode(true);
                    row.querySelectorAll('[name]').forEach(function (field) {
                        field.name = field.name.replace(/^sample_[0-9]+_/, 'sample_' + index + '_');
                        field.id = 'dynamic-' + field.name;
                    });
                    body.appendChild(row);
                });
            }
        }
        fill(target);
        if (window.reindexSampleRows) window.reindexSampleRows();
        if (window.evaluateConditionalLogic) window.evaluateConditionalLogic();
        restored = true;
    });
    if (orgType) orgType.addEventListener('change', organization);
    function initialize() {
        fill(form);
        organization();
        if (!service) return;
        Array.from(service.options).forEach(function (option) {
            const channel = option.dataset.channelAvailability;
            option.disabled = Boolean(option.value && channel !== 'BOTH' && channel !== 'GENOCLAB');
            option.hidden = option.disabled;
        });
        if (!saved.service_id) {
            const code = new URLSearchParams(window.location.search).get('service');
            const option = Array.from(service.options).find(function (item) { return item.dataset.code === code && !item.disabled; });
            if (option) service.value = option.value;
        }
        if (service.selectedOptions[0]?.disabled) service.value = '';
        if (service.value) service.dispatchEvent(new Event('change', {bubbles: true}));
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(initialize, 0); });
    else setTimeout(initialize, 0);
}());
