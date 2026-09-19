(function () {
    'use strict';
    function update() {
        if (window.PlagenorCostCalculator) window.PlagenorCostCalculator.updateCostEstimate();
    }
    function conditional() {
        const groups = Array.from(document.querySelectorAll('#dynamic-service-form [data-conditional-logic]'));
        for (let pass = 0; pass < 10; pass++) {
            let changed = false;
            groups.forEach(function (group) {
                const rules = JSON.parse(group.dataset.conditionalLogic || '[]');
                if (!rules.length) return;
                let visible = false;
                let required = group.dataset.originalRequired === 'true';
                rules.forEach(function (rule) {
                    const fields = Array.from(document.getElementsByName('param_' + rule.trigger_field));
                    const values = fields.filter(f => !f.disabled && (f.type !== 'checkbox' || f.checked)).map(f => f.value);
                    if (fields.length && fields[0].type === 'checkbox' && !values.length) values.push('false');
                    if (!values.includes(rule.trigger_value)) return;
                    (rule.actions || []).forEach(function (action) {
                        if (action === 'show') visible = true;
                        if (action === 'hide') visible = false;
                        if (action === 'make_required') required = true;
                        if (action === 'make_optional') required = false;
                    });
                });
                if ((group.style.display !== 'none') !== visible) changed = true;
                group.style.display = visible ? '' : 'none';
                group.querySelectorAll('input,select,textarea').forEach(function (field) {
                    field.disabled = !visible;
                    field.required = visible && required;
                });
            });
            if (!changed) break;
        }
    }
    function initialize() {
        const container = document.getElementById('dynamic-service-form');
        if (!container) return;
        container.querySelectorAll('input[name],select[name],textarea[name]').forEach(function (field) {
            if (!field.id) field.id = 'dynamic-' + field.name;
            const group = field.closest('.form-group');
            const label = group && group.querySelector('label');
            if (label && !label.htmlFor) label.htmlFor = field.id;
            const cell = field.closest('td');
            if (cell) {
                const header = cell.closest('table').querySelectorAll('thead th')[cell.cellIndex];
                if (header) field.setAttribute('aria-label', header.textContent.trim());
            }
        });
        container.querySelectorAll('button.btn-danger').forEach(function (button) {
            button.setAttribute('aria-label', window.gettext ? gettext('Supprimer la ligne') : 'Supprimer la ligne');
            button.style.minWidth = '28px'; button.style.minHeight = '28px';
        });
        container.querySelectorAll('.sample-dynamic-table').forEach(function (table) {
            table.parentElement.tabIndex = 0;
            table.parentElement.setAttribute('role','region');
            table.parentElement.setAttribute('aria-label', window.gettext ? gettext('Échantillons') : 'Échantillons');
        });
        conditional();
    }
    window.evaluateConditionalLogic = conditional;
    window.handlePricingChange = function () { conditional(); update(); };
    window.updateCostEstimate = update;
    document.addEventListener('serviceFormLoaded', initialize);
    document.addEventListener('sampleRowAdded', initialize);
    document.addEventListener('change', function (event) {
        if (event.target.name && event.target.name.startsWith('param_')) conditional();
    });
    document.addEventListener('sampleRowDeleted', update);
    document.addEventListener('DOMContentLoaded', initialize);
}());
