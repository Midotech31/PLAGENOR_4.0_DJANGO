(function () {
    'use strict';
    document.addEventListener('DOMContentLoaded', function () {
        const source = document.getElementById('submitted-editor-data');
        const form = document.getElementById('service-editor');
        if (!source || !form) return;
        const values = JSON.parse(source.textContent);
        if (values.field_name || values.custom_fields_present) {
            document.getElementById('custom-fields-container').replaceChildren();
            window.fieldCount = 0;
            (values.field_name || []).forEach(function () { window.addFieldRow(); });
        }
        if (values.pd_base_non_pathogenic || values.pd_mult_key) {
            document.getElementById('pd-multiplier-rows').replaceChildren();
            (values.pd_mult_key || []).forEach(function () { window.addMultiplierRow(); });
        }
        Object.entries(values).forEach(function ([name, items]) {
            const fields = Array.from(form.elements).filter(function (field) { return field.name === name; });
            fields.forEach(function (field, index) {
                if (field.type === 'checkbox' || field.type === 'radio') field.checked = items.includes(field.value);
                else if (field.type !== 'file') field.value = items[index] === undefined ? '' : items[index];
                field.dispatchEvent(new Event('input', {bubbles: true}));
            });
        });
    });
}());
