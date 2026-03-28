/* PLAGENOR 4.0 — Main JS */

// HTMX: include CSRF token in all requests
document.body.addEventListener('htmx:configRequest', (e) => {
    e.detail.headers['X-CSRFToken'] =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1]
        || '';
});

// Notification badge refresh
function refreshNotificationCount() {
    fetch('/dashboard/api/notification-count/')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('notification-count');
            if (badge) {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'flex' : 'none';
            }
        })
        .catch(() => {});
}

setInterval(refreshNotificationCount, 30000);

// Language toggle
function toggleLanguage() {
    const form = document.getElementById('language-form');
    if (!form) return;
    const input = form.querySelector('[name=language]');
    input.value = input.value === 'fr' ? 'en' : 'fr';
    form.submit();
}

// Mobile sidebar toggle
function toggleSidebar() {
    document.querySelector('.sidebar')?.classList.toggle('open');
}

// Close sidebar on overlay click (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar?.classList.contains('open') && !sidebar.contains(e.target) && !e.target.closest('.topbar-hamburger')) {
        sidebar.classList.remove('open');
    }
});

// Dynamic service form loading
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('select[name="service_id"]').forEach(function(select) {
        select.addEventListener('change', function() {
            var serviceId = this.value;
            var container = document.getElementById('dynamic-service-form');
            if (!container) return;
            if (!serviceId) { container.innerHTML = ''; return; }
            var option = this.options[this.selectedIndex];
            var code = option.getAttribute('data-code') || '';
            if (code) {
                fetch('/dashboard/api/service-form/' + code + '/')
                    .then(function(r) { return r.text(); })
                    .then(function(html) { container.innerHTML = html; })
                    .catch(function() { container.innerHTML = ''; });
            }
        });
    });
});

// Role selector (registration page)
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.role-option').forEach(option => {
        option.addEventListener('click', () => {
            document.querySelectorAll('.role-option').forEach(o => o.classList.remove('selected'));
            option.classList.add('selected');
            option.querySelector('input[type=radio]').checked = true;
        });
    });
});

// Dynamic sample table row management
var sampleRowCount = 1;

function addSampleRow() {
    var tbody = document.getElementById('sample-table-body');
    if (!tbody) { console.error('sample-table-body not found'); return; }

    // Get columns from table header data attributes
    var headerCells = tbody.closest('table').querySelectorAll('thead th[data-col]');
    var columns = [];
    headerCells.forEach(function(th) {
        columns.push(th.getAttribute('data-col'));
    });

    if (columns.length === 0) {
        // Fallback: parse from first row input names
        var firstInputs = tbody.querySelectorAll('tr:first-child input[name^="sample_"]');
        firstInputs.forEach(function(input) {
            var parts = input.name.split('_');
            if (parts.length >= 3) {
                columns.push(parts.slice(2).join('_'));
            }
        });
    }

    if (columns.length === 0) { console.error('No columns found'); return; }

    sampleRowCount++;
    var tr = document.createElement('tr');
    columns.forEach(function(col) {
        var td = document.createElement('td');
        td.style.cssText = 'padding:4px; border:1px solid #e2e8f0;';
        var input = document.createElement('input');
        input.type = 'text';
        input.name = 'sample_' + sampleRowCount + '_' + col;
        input.className = 'form-control';
        input.style.fontSize = '0.85rem';
        td.appendChild(input);
        tr.appendChild(td);
    });
    var tdBtn = document.createElement('td');
    tdBtn.style.cssText = 'padding:4px; border:1px solid #e2e8f0; text-align:center;';
    tdBtn.innerHTML = '<button type="button" class="btn btn-sm btn-danger" onclick="this.closest(\'tr\').remove()" style="padding:2px 8px;">&times;</button>';
    tr.appendChild(tdBtn);
    tbody.appendChild(tr);
}

// Cost estimation - update when samples change
function updateCostEstimate() {
    var box = document.getElementById('cost-estimate-box');
    if (!box) return;
    var pricingStr = box.getAttribute('data-pricing');
    if (!pricingStr) return;

    try {
        var pricing = JSON.parse(pricingStr.replace(/'/g, '"'));
        var rows = document.querySelectorAll('#sample-table-body tr').length || 1;
        var basePrice = pricing.base_price;
        var total = 0;

        if (typeof basePrice === 'object') {
            var unitPrice = basePrice.non_pathogenic || basePrice[Object.keys(basePrice)[0]] || 0;
            total = rows * unitPrice;
        } else {
            total = rows * (basePrice || pricing.unit_price || 0);
        }

        var display = document.getElementById('cost-estimate');
        if (display) display.textContent = total.toLocaleString('fr-FR') + ' DA';
    } catch(e) { console.log('Cost calc error:', e); }
}

// Hook cost estimation into sample row management
var _origAddSampleRow = window.addSampleRow;
if (typeof _origAddSampleRow === 'function') {
    window.addSampleRow = function() {
        _origAddSampleRow();
        updateCostEstimate();
    };
}

// Observe DOM changes in sample table for cost updates
document.addEventListener('DOMContentLoaded', function() {
    var costObserverTbody = document.getElementById('sample-table-body');
    if (costObserverTbody) {
        var costObserver = new MutationObserver(updateCostEstimate);
        costObserver.observe(costObserverTbody, { childList: true });
        updateCostEstimate();
    }
});

// EGTP-IMT: When pathogenic is checked, force Disposable target type
document.addEventListener('change', function(e) {
    if (e.target.name === 'param_pathogenic') {
        var targetSelect = document.querySelector('[name="param_maldi_target_type"]');
        if (!targetSelect) return;

        var isPathogenic = e.target.type === 'checkbox' ? e.target.checked : (e.target.value === 'true' || e.target.value === 'True');

        if (isPathogenic) {
            targetSelect.value = 'Disposable';
            targetSelect.disabled = true;
            // Add hidden input to ensure value is submitted (disabled fields don't submit)
            var hidden = document.getElementById('pathogen_target_hidden');
            if (!hidden) {
                hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.id = 'pathogen_target_hidden';
                hidden.name = 'param_maldi_target_type';
                hidden.value = 'Disposable';
                targetSelect.parentElement.appendChild(hidden);
            }
            // Show safety notice
            var hint = document.getElementById('pathogen-safety-hint');
            if (!hint) {
                hint = document.createElement('div');
                hint.id = 'pathogen-safety-hint';
                hint.style.cssText = 'color:#dc2626; margin-top:6px; font-size:0.8rem; padding:8px; background:#fef2f2; border-radius:6px; border:1px solid #fecaca;';
                hint.innerHTML = '<strong>Sécurité biologique:</strong> Les isolats pathogènes nécessitent obligatoirement une cible MALDI jetable (Disposable).';
                targetSelect.parentElement.appendChild(hint);
            }
            hint.style.display = 'block';
        } else {
            targetSelect.disabled = false;
            var hidden = document.getElementById('pathogen_target_hidden');
            if (hidden) hidden.remove();
            var hint = document.getElementById('pathogen-safety-hint');
            if (hint) hint.style.display = 'none';
        }
    }
});
