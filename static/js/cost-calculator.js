/** Canonical estimates; financial calculations are performed on the server. */
(function () {
    'use strict';
    let timer, pending, serial = 0;
    async function calculate() {
        const box = document.getElementById('cost-estimate-box');
        const output = document.getElementById('cost-estimate');
        if (!box || !output || !box.dataset.estimateUrl) return;
        const form = box.closest('form');
        if (!form) return;
        if (pending) pending.abort();
        pending = new AbortController();
        const requestSerial = ++serial;
        output.textContent = '—';
        try {
            const data = new FormData(form);
            // Never send uploaded files for a price preview.
            for (const [key, value] of Array.from(data.entries())) {
                if (value instanceof File) data.delete(key);
            }
            const response = await fetch(box.dataset.estimateUrl, {
                method: 'POST', body: data, credentials: 'same-origin',
                signal: pending.signal
            });
            if (!response.ok) return;
            const result = await response.json();
            if (requestSerial !== serial || !box.isConnected) return;
            if (result.visible && Number.isFinite(Number(result.total))) {
                output.textContent = Number(result.total).toLocaleString(document.documentElement.lang || 'fr',
                    {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' DA';
            }
        } catch (error) {
            if (error.name !== 'AbortError') output.textContent = '—';
        }
        document.dispatchEvent(new Event('costUpdated'));
    }
    function updateCostEstimate() {
        clearTimeout(timer);
        // Invalidate stale responses as soon as a field changes.
        serial += 1;
        if (pending) pending.abort();
        const output = document.getElementById('cost-estimate');
        if (output) output.textContent = '—';
        timer = setTimeout(calculate, 200);
    }
    ['input', 'change', 'sampleRowAdded', 'sampleRowDeleted', 'costUpdateRequested', 'serviceFormLoaded'].forEach(
        event => document.addEventListener(event, updateCostEstimate));
    document.addEventListener('DOMContentLoaded', updateCostEstimate);
    window.PlagenorCostCalculator = {updateCostEstimate};
    window.updateCostEstimate = updateCostEstimate;
})();
