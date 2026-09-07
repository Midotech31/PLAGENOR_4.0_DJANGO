/** Live estimates use the same server resolver as submitted requests. */
(function () {
    'use strict';
    let timer, controller, generation = 0;

    function updateCostEstimate() {
        clearTimeout(timer);
        if (controller) controller.abort();
        const current = ++generation;
        const config = document.getElementById('pricing-config');
        const output = document.getElementById('cost-estimate');
        if (!config || !output) return;
        output.textContent = '—';
        output.removeAttribute('data-amount');
        document.dispatchEvent(new Event('costUpdated'));
        timer = setTimeout(async function () {
            const form = config.closest('form');
            if (!form || !config.isConnected) return;
            const body = new FormData();
            for (const [key, value] of new FormData(form)) {
                if (key.startsWith('param_') || key.startsWith('sample_') || key === 'urgency') {
                    if (typeof value === 'string') body.append(key, value);
                }
            }
            body.set('channel', config.dataset.channel || 'GENOCLAB');
            const csrf = form.querySelector('[name="csrfmiddlewaretoken"]');
            if (csrf) body.set('csrfmiddlewaretoken', csrf.value);
            controller = new AbortController();
            try {
                const response = await fetch('/dashboard/api/estimate/' + encodeURIComponent(config.dataset.serviceCode) + '/', {
                    method: 'POST', credentials: 'same-origin', body, signal: controller.signal,
                    headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                if (!response.ok) throw new Error('Estimate unavailable');
                const result = await response.json();
                if (current !== generation || !output.isConnected) return;
                if (result.visible && Number.isFinite(Number(result.total))) {
                    output.dataset.amount = result.total;
                    output.textContent = new Intl.NumberFormat(document.documentElement.lang || 'fr', {
                        minimumFractionDigits: 2, maximumFractionDigits: 2
                    }).format(Number(result.total)) + ' DA';
                } else {
                    output.textContent = config.dataset.unavailable;
                }
            } catch (error) {
                if (error.name === 'AbortError' || current !== generation || !output.isConnected) return;
                output.textContent = config.dataset.unavailable;
            }
            document.dispatchEvent(new Event('costUpdated'));
        }, 250);
    }
    window.PlagenorCostCalculator = {updateCostEstimate};
    document.addEventListener('input', function (event) {
        if (event.target.matches('[name^="param_"], [name^="sample_"], [name="urgency"]')) updateCostEstimate();
    });
    document.addEventListener('change', function (event) {
        if (event.target.matches('[name^="param_"], [name^="sample_"], [name="urgency"]')) updateCostEstimate();
    });
    document.addEventListener('DOMContentLoaded', updateCostEstimate);
})();
