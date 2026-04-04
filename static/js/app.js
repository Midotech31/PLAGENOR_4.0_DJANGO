/* PLAGENOR 4.0 — Main JS */

// =============================================================================
// PAGE TRANSITIONS & ANIMATIONS
// =============================================================================

// Clickable table rows — navigate to data-href on click
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('tr.clickable-row[data-href]').forEach(function (row) {
        row.addEventListener('click', function () {
            window.location.href = row.dataset.href;
        });
    });
    
    // Page ready animation
    document.body.classList.add('page-ready');
});

// HTMX: include CSRF token in all requests
document.body.addEventListener('htmx:configRequest', (e) => {
    e.detail.headers['X-CSRFToken'] =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1]
        || '';
});

// HTMX: Enhanced page transitions
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    const loadingBar = document.getElementById('loading-bar');
    if (loadingBar) {
        loadingBar.classList.add('active');
        loadingBar.style.transform = 'scaleX(0)';
        loadingBar.offsetHeight; // Trigger reflow
        loadingBar.style.transform = 'scaleX(0.5)';
    }
});

document.body.addEventListener('htmx:afterSwap', function(evt) {
    const loadingBar = document.getElementById('loading-bar');
    if (loadingBar) {
        loadingBar.classList.remove('active');
        loadingBar.style.transform = 'scaleX(1)';
    }
    
    // Re-trigger animations for newly loaded content
    const newContent = evt.detail.target;
    if (newContent) {
        const animatedElements = newContent.querySelectorAll('.card, .kpi-card');
        animatedElements.forEach((el, index) => {
            el.style.animation = 'none';
            el.offsetHeight; // Trigger reflow
            el.style.animation = null;
            el.style.animationDelay = (index * 0.05) + 's';
        });
    }
});

document.body.addEventListener('htmx:afterSettle', function() {
    // Smooth scroll to top after content swap
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Language toggle
function toggleLanguage() {
    const form = document.getElementById('language-form');
    if (!form) return;
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
            if (!serviceId) { 
                container.innerHTML = ''; 
                return; 
            }
            var option = this.options[this.selectedIndex];
            var code = option.getAttribute('data-code') || '';
            if (code) {
                fetch('/dashboard/api/service-form/' + code + '/')
                    .then(function(r) { return r.text(); })
                    .then(function(html) {
                        container.innerHTML = html;
                        
                        // Dispatch event to notify that form is loaded
                        document.dispatchEvent(new CustomEvent('serviceFormLoaded', {
                            detail: { serviceCode: code, serviceId: serviceId }
                        }));
                        
                        // Trigger cost calculation after a short delay to ensure scripts run
                        setTimeout(function() {
                            if (window.PlagenorCostCalculator) {
                                window.PlagenorCostCalculator.updateCostEstimate();
                            } else {
                                // Fallback: dispatch cost update request
                                document.dispatchEvent(new Event('costUpdateRequested'));
                            }
                        }, 300);
                    })
                    .catch(function(err) { 
                        console.error('Failed to load service form:', err);
                        container.innerHTML = ''; 
                    });
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

    var headerCells = tbody.closest('table').querySelectorAll('thead th[data-col]');
    var columns = [];
    headerCells.forEach(function(th) {
        columns.push({
            name: th.getAttribute('data-col'),
            type: th.getAttribute('data-type') || 'text',
        });
    });

    if (columns.length === 0) {
        var firstInputs = tbody.querySelectorAll('tr:first-child [name^="sample_"]');
        firstInputs.forEach(function(el) {
            var parts = el.name.split('_');
            if (parts.length >= 3) {
                columns.push({
                    name: parts.slice(2).join('_'),
                    type: el.tagName === 'SELECT' ? 'select' : 'text',
                });
            }
        });
    }

    if (columns.length === 0) { console.error('No columns found'); return; }

    sampleRowCount++;
    var rowIndex = tbody.querySelectorAll('tr').length;
    var tr = document.createElement('tr');
    columns.forEach(function(col) {
        var td = document.createElement('td');
        td.style.cssText = 'padding:4px; border:1px solid #e2e8f0;';

        var colNameLower = col.name.toLowerCase();
        if (colNameLower === 'n°' || colNameLower === 'no' || colNameLower === 'num' || colNameLower === 'n°') {
            var input = document.createElement('input');
            input.type = 'text';
            input.name = 'sample_' + sampleRowCount + '_' + col.name;
            input.className = 'form-control';
            input.style.cssText = 'font-size:0.85rem; background:#f8fafc;';
            input.value = rowIndex + 1;
            input.readOnly = true;
            td.appendChild(input);
        } else if (col.type === 'select' || col.type === 'enum' || col.type === 'dropdown') {
            var th = tbody.closest('table').querySelector('thead th[data-col="' + col.name + '"]');
            var select = document.createElement('select');
            select.name = 'sample_' + sampleRowCount + '_' + col.name;
            select.className = 'form-control';
            select.style.fontSize = '0.85rem';
            select.innerHTML = '<option value="">Choisir</option>';
            if (th) {
                var firstSelect = tbody.querySelector('tr:first-child select[name*="' + col.name + '"]');
                if (firstSelect) {
                    select.innerHTML = firstSelect.innerHTML;
                }
            }
            td.appendChild(select);
        } else if (col.type === 'number' || col.type === 'integer' || col.type === 'float') {
            var input = document.createElement('input');
            input.type = 'number';
            input.name = 'sample_' + sampleRowCount + '_' + col.name;
            input.className = 'form-control';
            input.style.fontSize = '0.85rem';
            if (col.type === 'float') input.step = '0.01';
            td.appendChild(input);
        } else {
            var input = document.createElement('input');
            input.type = 'text';
            input.name = 'sample_' + sampleRowCount + '_' + col.name;
            input.className = 'form-control';
            input.style.cssText = 'font-size:0.85rem; min-width: 120px;';
            if (colNameLower === 'code') {
                input.maxLength = 50;
            }
            td.appendChild(input);
        }
        tr.appendChild(td);
    });
    var tdBtn = document.createElement('td');
    tdBtn.style.cssText = 'padding:4px; border:1px solid #e2e8f0; text-align:center;';
    tdBtn.innerHTML = '<button type="button" class="btn btn-sm btn-danger" onclick="deleteSampleRow(this)" style="padding:2px 8px;">&times;</button>';
    tr.appendChild(tdBtn);
    tbody.appendChild(tr);
    
    // Trigger cost update via event (form will handle it)
    document.dispatchEvent(new Event('sampleRowAdded'));
}

function deleteSampleRow(btn) {
    var tr = btn.closest('tr');
    if (tr) {
        tr.remove();
        reindexSampleRows();
        document.dispatchEvent(new Event('sampleRowDeleted'));
    }
}

function reindexSampleRows() {
    var tbody = document.getElementById('sample-table-body');
    if (!tbody) return;
    
    var rows = tbody.querySelectorAll('tr');
    rows.forEach(function(row, index) {
        var numInput = row.querySelector('input[name*="n°"], input[name*="N°"], input[name*="no"], input[name*="num"], input[name*="Num"]');
        if (numInput) {
            numInput.value = index + 1;
        }
    });
}

// Event delegation for cost estimation - listens to all changes on the form
document.addEventListener('change', function(e) {
    // Trigger cost update for pricing-related fields
    if (e.target.name && e.target.name.startsWith('param_')) {
        document.dispatchEvent(new CustomEvent('costUpdateRequested', { detail: { field: e.target.name } }));
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
            var hidden = document.getElementById('pathogen_target_hidden');
            if (!hidden) {
                hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.id = 'pathogen_target_hidden';
                hidden.name = 'param_maldi_target_type';
                hidden.value = 'Disposable';
                targetSelect.parentElement.appendChild(hidden);
            }
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

// Form preview modal before submission
function showFormPreview(formEl) {
    if (!formEl) return;

    var existing = document.getElementById('form-preview-overlay');
    if (existing) existing.remove();

    var serviceSelect = formEl.querySelector('select[name="service_id"]');
    var serviceName = serviceSelect ? (serviceSelect.options[serviceSelect.selectedIndex].text || '—') : '—';

    var title = (formEl.querySelector('[name="title"]') || {}).value || '—';
    var description = (formEl.querySelector('[name="description"]') || {}).value || '—';
    var urgencySelect = formEl.querySelector('[name="urgency"]');
    var urgency = urgencySelect ? (urgencySelect.options[urgencySelect.selectedIndex].text || 'Normal') : 'Normal';

    var balanceInput = formEl.querySelector('[name="declared_balance"]');
    var balanceHtml = '';
    if (balanceInput) {
        balanceHtml = '<div class="preview-row"><span class="preview-label">Solde IBTIKAR déclaré</span><span class="preview-value">' + parseFloat(balanceInput.value || 0).toLocaleString('fr-FR') + ' DA</span></div>';
    }

    var paramsHtml = '';
    var paramInputs = formEl.querySelectorAll('[name^="param_"]');
    paramInputs.forEach(function(input) {
        var label = '';
        var value = '';
        var name = input.name.replace('param_', '');

        var formGroup = input.closest('.form-group');
        if (formGroup) {
            var lbl = formGroup.querySelector('label');
            if (lbl) label = lbl.textContent.replace(' *', '').trim();
        }
        if (!label) label = name.replace(/_/g, ' ');

        if (input.type === 'checkbox') {
            value = input.checked ? 'Oui' : 'Non';
        } else if (input.tagName === 'SELECT') {
            value = input.options[input.selectedIndex] ? input.options[input.selectedIndex].text : input.value;
        } else if (input.type === 'hidden') {
            return;
        } else {
            value = input.value || '—';
        }

        if (value) {
            paramsHtml += '<div class="preview-row"><span class="preview-label">' + label + '</span><span class="preview-value">' + value + '</span></div>';
        }
    });

    var sampleHtml = '';
    var sampleTable = document.getElementById('sample-table');
    if (sampleTable) {
        var headers = [];
        sampleTable.querySelectorAll('thead th[data-col]').forEach(function(th) {
            headers.push(th.textContent.trim());
        });
        var rows = [];
        document.querySelectorAll('#sample-table-body tr').forEach(function(tr) {
            var cells = [];
            tr.querySelectorAll('input[type="text"]').forEach(function(input) {
                cells.push(input.value || '—');
            });
            if (cells.length > 0) rows.push(cells);
        });

        if (headers.length > 0 && rows.length > 0) {
            sampleHtml = '<table style="width:100%; border-collapse:collapse; font-size:0.85rem;">';
            sampleHtml += '<thead><tr>';
            sampleHtml += '<th style="padding:8px 10px; border:1px solid #e2e8f0; background:#f8fafc; text-align:left; font-weight:600;">#</th>';
            headers.forEach(function(h) {
                sampleHtml += '<th style="padding:8px 10px; border:1px solid #e2e8f0; background:#f8fafc; text-align:left; font-weight:600;">' + h + '</th>';
            });
            sampleHtml += '</tr></thead><tbody>';
            rows.forEach(function(row, idx) {
                sampleHtml += '<tr>';
                sampleHtml += '<td style="padding:6px 10px; border:1px solid #e2e8f0;">' + (idx + 1) + '</td>';
                row.forEach(function(cell) {
                    sampleHtml += '<td style="padding:6px 10px; border:1px solid #e2e8f0;">' + cell + '</td>';
                });
                sampleHtml += '</tr>';
            });
            sampleHtml += '</tbody></table>';
        }
    }

    var costEl = document.getElementById('cost-estimate');
    var costText = costEl ? costEl.textContent : '—';

    var html = '<div id="form-preview-overlay" style="position:fixed; inset:0; z-index:9999; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.5); backdrop-filter:blur(4px); animation:fadeIn 0.2s ease;">';
    html += '<div style="background:#fff; border-radius:16px; max-width:700px; width:95%; max-height:90vh; overflow-y:auto; box-shadow:0 25px 50px rgba(0,0,0,0.15); animation:slideUp 0.3s ease;">';

    html += '<div style="padding:24px 28px 16px; border-bottom:1px solid #e2e8f0;">';
    html += '<h2 style="margin:0; font-size:1.25rem; color:#1e293b;">Vérification de la demande</h2>';
    html += '<p style="margin:6px 0 0; font-size:0.85rem; color:#64748b;">Veuillez vérifier les informations avant de soumettre.</p>';
    html += '</div>';

    html += '<div style="padding:20px 28px;">';

    html += '<div class="preview-section">';
    html += '<h4 style="font-size:0.9rem; color:#475569; margin:0 0 10px; text-transform:uppercase; letter-spacing:0.5px;">Service</h4>';
    html += '<div style="padding:10px 14px; background:#f8fafc; border-radius:8px; font-weight:600;">' + serviceName + '</div>';
    html += '</div>';

    if (paramsHtml) {
        html += '<div class="preview-section" style="margin-top:18px;">';
        html += '<h4 style="font-size:0.9rem; color:#475569; margin:0 0 10px; text-transform:uppercase; letter-spacing:0.5px;">Paramètres du service</h4>';
        html += '<div style="background:#f8fafc; border-radius:8px; padding:8px 14px;">' + paramsHtml + '</div>';
        html += '</div>';
    }

    if (sampleHtml) {
        html += '<div class="preview-section" style="margin-top:18px;">';
        html += '<h4 style="font-size:0.9rem; color:#475569; margin:0 0 10px; text-transform:uppercase; letter-spacing:0.5px;">Tableau des échantillons</h4>';
        html += '<div style="border-radius:8px; overflow:hidden; border:1px solid #e2e8f0;">' + sampleHtml + '</div>';
        html += '</div>';
    }

    if (costText && costText !== '—') {
        html += '<div class="preview-section" style="margin-top:18px;">';
        html += '<div style="padding:12px 14px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; font-weight:600;">Coût estimé: ' + costText + '</div>';
        html += '</div>';
    }

    html += '<div class="preview-section" style="margin-top:18px;">';
    html += '<h4 style="font-size:0.9rem; color:#475569; margin:0 0 10px; text-transform:uppercase; letter-spacing:0.5px;">Détails de la demande</h4>';
    html += '<div style="background:#f8fafc; border-radius:8px; padding:8px 14px;">';
    html += '<div class="preview-row"><span class="preview-label">Titre</span><span class="preview-value">' + title + '</span></div>';
    html += '<div class="preview-row"><span class="preview-label">Description</span><span class="preview-value">' + description + '</span></div>';
    html += '<div class="preview-row"><span class="preview-label">Urgence</span><span class="preview-value">' + urgency + '</span></div>';
    html += balanceHtml;
    html += '</div>';
    html += '</div>';

    html += '</div>';

    html += '<div style="padding:16px 28px 24px; display:flex; gap:12px; justify-content:flex-end; border-top:1px solid #e2e8f0;">';
    html += '<button type="button" onclick="closeFormPreview()" style="padding:10px 24px; border:1px solid #d1d5db; background:#fff; border-radius:8px; cursor:pointer; font-size:0.9rem; color:#475569; transition:all 0.15s;">Modifier</button>';
    html += '<button type="button" onclick="confirmFormSubmit()" style="padding:10px 24px; border:none; background:#2563eb; color:#fff; border-radius:8px; cursor:pointer; font-size:0.9rem; font-weight:600; transition:all 0.15s;">Confirmer et soumettre</button>';
    html += '</div>';

    html += '</div></div>';

    var style = document.createElement('style');
    style.id = 'preview-modal-styles';
    style.textContent = '.preview-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f1f5f9;}.preview-row:last-child{border-bottom:none;}.preview-label{color:#64748b;font-size:0.85rem;}.preview-value{font-weight:500;color:#1e293b;font-size:0.85rem;max-width:60%;text-align:right;}@keyframes fadeIn{from{opacity:0}to{opacity:1}}@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}';
    if (!document.getElementById('preview-modal-styles')) document.head.appendChild(style);

    document.body.insertAdjacentHTML('beforeend', html);
    window._previewFormEl = formEl;
}

function closeFormPreview() {
    var overlay = document.getElementById('form-preview-overlay');
    if (overlay) overlay.remove();
    window._previewFormEl = null;
}

function confirmFormSubmit() {
    var formEl = window._previewFormEl;
    closeFormPreview();
    if (formEl) formEl.submit();
}